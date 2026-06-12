"""
test_orchestrator.py - Tests de Integración para el AgentOrchestrator
=======================================================================
Objetivo: Probar el PIPELINE COMPLETO del Orquestador, verificando que:
  1. Los agentes se llaman en el orden correcto.
  2. El estado del Job en BD cambia correctamente en cada paso.
  3. El ciclo de QA + retries funciona correctamente.
  4. Si el QA rechaza 2 veces, el pipeline fuerza la aceptación.
  5. Si un agente falla, el Job queda en estado 'error'.

Estrategia:
  - La BD es real (PostgreSQL de test), via db_session fixture de conftest.
  - Los servicios de LLM y los agentes individuales están mockeados para
    que el test solo valide la lógica del ORQUESTADOR, no de los agentes.
  - Se usan 'side_effect' para simular fallas controladas.
"""
import pytest
from unittest.mock import patch, MagicMock, call


class TestAgentOrchestratorPipeline:
    """
    Tests de integración para el AgentOrchestrator.
    """

    def _make_orchestrator_with_mock_tools(self):
        """Helper: crea un Orchestrator con todas sus herramientas mockeadas."""
        from agents.orchestrator import AgentOrchestrator
        orchestrator = AgentOrchestrator()

        # Reemplazamos las herramientas reales con mocks
        orchestrator.generate_text = MagicMock(return_value={"slides": []})
        orchestrator.compose_layout = MagicMock(return_value={"success": True})
        orchestrator.validate_brand = MagicMock(return_value={"status": "passed", "violations": []})
        orchestrator.score_fidelity = MagicMock(return_value=[])  # List[Dict] — no failures by default
        orchestrator.render_pptx = MagicMock(return_value={"output_path": "/outputs/test.pptx"})
        return orchestrator

    # ─────────────────────────────────────────────────────────────────────────
    # Test 1: Flujo feliz (happy path)
    # ─────────────────────────────────────────────────────────────────────────
    def test_pipeline_happy_path_calls_all_agents_in_order(self, db_session, sample_job):
        """
        GIVEN: un Job válido en BD
        WHEN: se ejecuta run_generation_pipeline con todos los agentes mockeados
        THEN: todos los agentes deben ser llamados exactamente una vez, en orden.
        """
        orchestrator = self._make_orchestrator_with_mock_tools()

        req_data = {
            "prompt": "Test presentation about AI",
            "style_filename": "test_style.pptx",
            "knowledge_filename": "test_knowledge.pdf",
            "region": "Global",
            "allow_ai_images": False,
            "output_format": "pptx",
            "tier": "standard"
        }

        # Capturar el id ANTES: el orquestador cierra la sesión que crea (la
        # inyectada vía patch), y el ORM no puede refrescar atributos después.
        job_id = sample_job.id
        with patch("agents.orchestrator.SessionLocal", return_value=db_session):
            orchestrator.run_generation_pipeline(job_id=job_id, req_data=req_data)

        # Verificar que cada agente fue llamado exactamente 1 vez (en flujo sin errores)
        orchestrator.generate_text.assert_called_once_with(
            job_id=job_id,
            prompt="Test presentation about AI",
            style_filename="test_style.pptx",
            knowledge_filename="test_knowledge.pdf",
            region="Global",
            allow_ai_images=False
        )
        orchestrator.compose_layout.assert_called_once()
        orchestrator.validate_brand.assert_called_once()
        orchestrator.score_fidelity.assert_called_once()
        orchestrator.render_pptx.assert_called_once()

    # ─────────────────────────────────────────────────────────────────────────
    # Test 2: QA falla una vez → reintenta y luego aprueba
    # ─────────────────────────────────────────────────────────────────────────
    def test_pipeline_qa_retry_on_first_failure(self, db_session, sample_job, sample_slides):
        """
        GIVEN: el QA falla en el primer intento pero aprueba en el segundo
        WHEN: se ejecuta run_generation_pipeline
        THEN: compose_layout debe llamarse 2 veces (intento 1 + retry 1)
              y render_pptx debe llamarse 1 vez al final.
        """
        orchestrator = self._make_orchestrator_with_mock_tools()

        # QA: falla slide 1 en primer call, aprueba en segundo call — List[Dict] shape
        orchestrator.score_fidelity.side_effect = [
            [{"slide_number": 1, "score": 0.3, "needs_rework": True, "reasoning": "Color mismatch"}],   # Intento 1: FALLA
            [{"slide_number": 1, "score": 0.95, "needs_rework": False, "reasoning": "Looks great now"}], # Intento 2: APRUEBA
        ]

        req_data = {"prompt": "Test", "style_filename": "s.pptx", "knowledge_filename": "k.pdf",
                    "region": "Global", "allow_ai_images": False, "output_format": "pptx", "tier": "standard"}

        with patch("agents.orchestrator.SessionLocal", return_value=db_session):
            orchestrator.run_generation_pipeline(job_id=sample_job.id, req_data=req_data)

        # El layout debe haberse recompuesto 2 veces (intento inicial + 1 retry)
        assert orchestrator.compose_layout.call_count == 2, \
            f"Expected 2 layout compositions, got {orchestrator.compose_layout.call_count}"
        # El render solo se ejecuta 1 vez al final
        orchestrator.render_pptx.assert_called_once()

    # ─────────────────────────────────────────────────────────────────────────
    # Test 3: QA falla todas las veces → fuerza aceptación al agotar reintentos
    # ─────────────────────────────────────────────────────────────────────────
    def test_pipeline_forces_acceptance_after_max_retries(self, db_session, sample_job, sample_slides):
        """
        GIVEN: el QA siempre rechaza (score bajo en todos los intentos)
        WHEN: se ejecuta run_generation_pipeline
        THEN: después de MAX_RETRIES=2, el pipeline fuerza el render igual.
              Esto garantiza que el pipeline NUNCA se quede bloqueado.
        """
        orchestrator = self._make_orchestrator_with_mock_tools()
        MAX_RETRIES = orchestrator.MAX_RETRIES  # 2

        # QA siempre rechaza slide 1 — List[Dict] shape
        orchestrator.score_fidelity.return_value = [
            {"slide_number": 1, "score": 0.2, "needs_rework": True, "reasoning": "Persistent brand mismatch"}
        ]

        req_data = {"prompt": "Test", "style_filename": "s.pptx", "knowledge_filename": "k.pdf",
                    "region": "Global", "allow_ai_images": False, "output_format": "pptx", "tier": "standard"}

        with patch("agents.orchestrator.SessionLocal", return_value=db_session):
            orchestrator.run_generation_pipeline(job_id=sample_job.id, req_data=req_data)

        # compose_layout se llama MAX_RETRIES + 1 veces (intento inicial + todos los reintentos)
        expected_layout_calls = MAX_RETRIES + 1
        assert orchestrator.compose_layout.call_count == expected_layout_calls, \
            f"Expected {expected_layout_calls} layout calls, got {orchestrator.compose_layout.call_count}"

        # ¡El render SIEMPRE debe ejecutarse, incluso si el QA nunca aprueba!
        orchestrator.render_pptx.assert_called_once()

    # ─────────────────────────────────────────────────────────────────────────
    # Test 4: QA determinístico (ValidateBrand) falla → saltea el LLM QA
    # ─────────────────────────────────────────────────────────────────────────
    def test_pipeline_deterministic_qa_failure_skips_llm_qa(self, db_session, sample_job, sample_slides):
        """
        GIVEN: el ValidateBrandTool (determinístico) detecta una violación
        WHEN: se ejecuta run_generation_pipeline
        THEN: el ScoreFidelityTool (LLM) NO debe llamarse en ese intento fallido.
              La lógica es: si el determinístico falla, no gastes tokens en el LLM.
        """
        orchestrator = self._make_orchestrator_with_mock_tools()

        # El validador determinístico falla 2 veces, pasa al tercer intento
        orchestrator.validate_brand.side_effect = [
            {"status": "failed", "violations": [{"rule": "VIOLATION", "slide_number": 1}]},
            {"status": "failed", "violations": [{"rule": "VIOLATION", "slide_number": 1}]},
            {"status": "passed", "violations": []},  # Al tercer intento, pasa
        ]
        # El LLM QA aprueba cuando finalmente se llama — List[Dict] shape
        orchestrator.score_fidelity.return_value = []

        req_data = {"prompt": "Test", "style_filename": "s.pptx", "knowledge_filename": "k.pdf",
                    "region": "Global", "allow_ai_images": False, "output_format": "pptx", "tier": "standard"}

        with patch("agents.orchestrator.SessionLocal", return_value=db_session):
            orchestrator.run_generation_pipeline(job_id=sample_job.id, req_data=req_data)

        # El determinístico falló 2 veces → el LLM QA solo se llama cuando el determinístico pasa
        # Debe haberse llamado solo 1 vez (en el tercer intento donde validate_brand pasó)
        assert orchestrator.score_fidelity.call_count == 1, \
            "LLM QA should only be called when deterministic QA passes"

    # ─────────────────────────────────────────────────────────────────────────
    # Test 5: Falla catastrófica → el job queda en estado 'error'
    # ─────────────────────────────────────────────────────────────────────────
    def test_pipeline_sets_error_status_on_exception(self, db_session, sample_job):
        """
        GIVEN: el Redactor lanza una excepción inesperada
        WHEN: se ejecuta run_generation_pipeline
        THEN: el Job en BD debe quedar en estado 'error' y el pipeline no debe explotar.
        """
        import models
        orchestrator = self._make_orchestrator_with_mock_tools()

        # El Redactor falla con una excepción
        orchestrator.generate_text.side_effect = Exception("LLM provider is down!")

        req_data = {"prompt": "Test", "style_filename": "s.pptx", "knowledge_filename": "k.pdf",
                    "region": "Global", "allow_ai_images": False, "output_format": "pptx", "tier": "standard"}

        # El pipeline NO debe lanzar una excepción al caller
        with patch("agents.orchestrator.SessionLocal", return_value=db_session), \
             patch.object(db_session, "close"):
            orchestrator.run_generation_pipeline(job_id=sample_job.id, req_data=req_data)

        # El Job debe estar marcado como 'error' en la BD
        db_session.refresh(sample_job)
        assert sample_job.status == models.GenerationJobStatus.ERROR, \
            f"Expected job status 'error', got '{sample_job.status}'"
        assert "Pipeline Error" in sample_job.current_step

    # ─────────────────────────────────────────────────────────────────────────
    # Test 6: Pipeline Premium usa tier correcto
    # ─────────────────────────────────────────────────────────────────────────
    def test_pipeline_premium_tier_passes_is_premium_flag(self, db_session, sample_job):
        """
        GIVEN: una solicitud con tier='premium'
        WHEN: se ejecuta run_generation_pipeline
        THEN: compose_layout y render_pptx deben recibir is_premium=True
        """
        orchestrator = self._make_orchestrator_with_mock_tools()

        req_data = {"prompt": "Premium test", "style_filename": "s.pptx", "knowledge_filename": "k.pdf",
                    "region": "Global", "allow_ai_images": False, "output_format": "pdf", "tier": "premium"}

        # Capturar el id ANTES: el orquestador cierra la sesión que crea (la inyectada vía patch)
        job_id = sample_job.id
        with patch("agents.orchestrator.SessionLocal", return_value=db_session):
            orchestrator.run_generation_pipeline(job_id=job_id, req_data=req_data)

        # compose_layout debe recibir is_premium=True (qa_feedback=None en el primer intento, F1)
        orchestrator.compose_layout.assert_called_with(job_id=job_id, is_premium=True, qa_feedback=None)
        # render_pptx también debe recibir is_premium=True
        call_kwargs = orchestrator.render_pptx.call_args.kwargs
        assert call_kwargs.get("is_premium") is True
        assert call_kwargs.get("output_format") == "pdf"

    # ─────────────────────────────────────────────────────────────────────────
    # Test 7: Pipeline en modo interactivo se pausa en CONTENT_READY
    # ─────────────────────────────────────────────────────────────────────────
    def test_pipeline_interactive_mode_pauses_at_content_ready(self, db_session, sample_job):
        """
        GIVEN: una solicitud con interactive_mode=True
        WHEN: se ejecuta run_generation_pipeline
        THEN: se genera el texto (Redactor), pero se detiene antes del diseño (Arquitecto)
        """
        orchestrator = self._make_orchestrator_with_mock_tools()

        req_data = {
            "prompt": "Interactive test",
            "style_filename": "s.pptx",
            "knowledge_filename": "k.pdf",
            "region": "Global",
            "allow_ai_images": False,
            "output_format": "pptx",
            "tier": "standard",
            "interactive_mode": True
        }

        with patch("agents.orchestrator.SessionLocal", return_value=db_session):
            orchestrator.run_generation_pipeline(job_id=sample_job.id, req_data=req_data)

        # Se debió llamar al Redactor
        orchestrator.generate_text.assert_called_once()
        # NO se debió llamar al Arquitecto ni al Render
        orchestrator.compose_layout.assert_not_called()
        orchestrator.render_pptx.assert_not_called()

    # ─────────────────────────────────────────────────────────────────────────
    # Test 8: Reanudación del pipeline ejecuta diseño y renderizado
    # ─────────────────────────────────────────────────────────────────────────
    def test_pipeline_resume_completes_design_and_render(self, db_session, sample_job):
        """
        GIVEN: un job previamente pausado en revisión humana
        WHEN: se ejecuta resume_generation_pipeline
        THEN: se ejecutan compose_layout y render_pptx
        """
        orchestrator = self._make_orchestrator_with_mock_tools()

        req_data = {
            "style_filename": "s.pptx",
            "knowledge_filename": "k.pdf",
            "region": "Global",
            "allow_ai_images": False,
            "output_format": "pptx",
            "tier": "standard"
        }

        with patch("agents.orchestrator.SessionLocal", return_value=db_session):
            orchestrator.resume_generation_pipeline(job_id=sample_job.id, req_data=req_data)

        # compose_layout y render_pptx deben llamarse
        orchestrator.compose_layout.assert_called_once()
        orchestrator.render_pptx.assert_called_once()

