"""
test_agents_unit.py - Tests Unitarios para los Agent Tools
===========================================================
Objetivo: Probar cada herramienta (Tool) de forma aislada.
  - Los LLM están mockeados (via conftest.py autouse fixture).
  - La BD usada es la BD de test real (PostgreSQL dedicada).
  - Cada test hace ROLLBACK automático (via fixture db_session).

Agentes probados:
  - ValidateBrandTool: Reglas deterministas de brand compliance.
  - ScoreFidelityTool: Validación híbrida con LLM mockeado.
  - ComposeLayoutTool: Asignación de layouts por el Arquitecto.
  - GenerateTextTool: Síntesis de contenido por el Redactor.
"""
import pytest
from unittest.mock import patch, MagicMock


# ─────────────────────────────────────────────────────────────────────────────
# Tests para ValidateBrandTool (QA Determinístico)
# ─────────────────────────────────────────────────────────────────────────────
class TestValidateBrandTool:
    """
    Tests para el validador determinístico de brand compliance.
    No usa LLM, no necesita mock adicional.
    """

    def test_validate_brand_passes_with_valid_slides(self, db_session, sample_slides, sample_job):
        """
        GIVEN: slides válidos (no usan logo en layout de alta resolución)
        WHEN: se ejecuta ValidateBrandTool
        THEN: el resultado debe ser 'passed' con 0 violaciones
        """
        from agents.qa_validator import ValidateBrandTool

        # Parchar SessionLocal para usar nuestra db_session de test
        with patch("agents.qa_validator.SessionLocal", return_value=db_session):
            tool = ValidateBrandTool()
            result = tool.run(job_id=sample_job.id)

        assert result["status"] == "passed", f"Expected 'passed', got: {result}"
        assert len(result["violations"]) == 0

    def test_validate_brand_detects_logo_as_background(self, db_session, sample_job, sample_brand):
        """
        GIVEN: un slide 'cover_hero' (alta resolución) con un logo asignado como imagen
        WHEN: se ejecuta ValidateBrandTool
        THEN: debe detectar la violación HI_RES_BACKGROUND_VIOLATION
        """
        import models
        from agents.qa_validator import ValidateBrandTool

        # Crear un asset tipo 'logos'
        logo_asset = models.BrandAsset(
            brand_id=sample_brand.id,
            category="logos",
            local_path="/assets/brands/test/logos/company_logo.png",
            file_hash="abc123test"
        )
        db_session.add(logo_asset)
        db_session.flush()

        # Crear un slide cover_hero (layout de alta resolución) con el logo asignado
        slide = models.PresentationSlide(
            job_id=sample_job.id,
            slide_number=99,
            title="Offending Cover Slide",
            layout_slug="cover_hero",   # Layout que exige foto de alta resolución
            assigned_image=str(logo_asset.id),  # Asignar el LOGO como imagen principal ← VIOLACIÓN
            status="planned",
        )
        db_session.add(slide)
        db_session.flush()

        with patch("agents.qa_validator.SessionLocal", return_value=db_session):
            tool = ValidateBrandTool()
            result = tool.run(job_id=sample_job.id)

        assert result["status"] == "failed", "Should fail with logo-as-background violation"
        assert len(result["violations"]) >= 1
        violation = result["violations"][0]
        assert violation["rule"] == "HI_RES_BACKGROUND_VIOLATION"
        assert violation["slide_number"] == 99

    def test_validate_brand_returns_correct_structure(self, db_session, sample_job):
        """
        GIVEN: cualquier job
        WHEN: se ejecuta ValidateBrandTool
        THEN: la respuesta siempre debe tener las claves 'status' y 'violations'
        """
        from agents.qa_validator import ValidateBrandTool

        with patch("agents.qa_validator.SessionLocal", return_value=db_session):
            tool = ValidateBrandTool()
            result = tool.run(job_id=sample_job.id)

        assert "status" in result
        assert "violations" in result
        assert isinstance(result["violations"], list)
        assert result["status"] in ["passed", "failed"]


# ─────────────────────────────────────────────────────────────────────────────
# Tests para ScoreFidelityTool (QA con LLM)
# ─────────────────────────────────────────────────────────────────────────────
class TestScoreFidelityTool:
    """
    Tests para el validador híbrido (LLM Judge).
    El LLM está mockeado via conftest.py, por lo que los tests son deterministas.
    """

    def test_score_fidelity_passes_when_llm_approves(self, db_session, sample_job, sample_slides, sample_brand):
        """
        GIVEN: un job con slides y visual DNA, y el LLM mock retorna score=0.92
        WHEN: se ejecuta ScoreFidelityTool
        THEN: needs_rework debe ser False
        """
        import models
        from agents.qa_validator import ScoreFidelityTool

        # Crear el BrandVisualDna para que el QA encuentre contexto de marca
        dna = db_session.query(models.BrandVisualDna).filter_by(brand_id=sample_brand.id).first()
        assert dna is not None, "BrandVisualDna should be created by sample_brand fixture"

        with patch("agents.qa_validator.SessionLocal", return_value=db_session):
            tool = ScoreFidelityTool()
            result = tool.run(job_id=sample_job.id)

        assert result["needs_rework"] is False
        assert result["score"] == 0.92  # Viene del mock en conftest.py
        assert "reasoning" in result

    def test_score_fidelity_triggers_rework_when_llm_rejects(self, db_session, sample_job, sample_slides, sample_brand):
        """
        GIVEN: el LLM mock devuelve score bajo (0.4) y needs_rework=True
        WHEN: se ejecuta ScoreFidelityTool
        THEN: needs_rework debe ser True y el job debe quedar en estado 'qa_failed'
        """
        import models
        from agents.qa_validator import ScoreFidelityTool

        # Sobreescribir el mock global con uno que rechaza
        low_score_response = {
            "score": 0.4,
            "needs_rework": True,
            "reasoning": "Mock: Brand alignment failed. Color palette mismatch."
        }

        with patch("agents.qa_validator.SessionLocal", return_value=db_session), \
             patch("agents.qa_validator.generate_json", return_value=low_score_response), \
             patch.object(db_session, "close"):
            tool = ScoreFidelityTool()
            result = tool.run(job_id=sample_job.id)

        assert result["needs_rework"] is True
        assert result["score"] == 0.4

        # Verificar que el estado del job en BD se actualizó
        db_session.refresh(sample_job)
        assert sample_job.status == models.GenerationJobStatus.QA_FAILED

    def test_score_fidelity_auto_passes_when_no_slides(self, db_session, sample_job):
        """
        GIVEN: un job sin slides en BD
        WHEN: se ejecuta ScoreFidelityTool
        THEN: debe auto-pasar (sin datos = no hay nada que rechazar)
        """
        from agents.qa_validator import ScoreFidelityTool

        with patch("agents.qa_validator.SessionLocal", return_value=db_session):
            tool = ScoreFidelityTool()
            result = tool.run(job_id=sample_job.id)

        # Sin slides, el QA no puede hacer nada → auto-pasa
        assert result.get("needs_rework") is False


# ─────────────────────────────────────────────────────────────────────────────
# Tests para GetSlideTypesTool (Arquitecto)
# ─────────────────────────────────────────────────────────────────────────────
class TestGetSlideTypesTool:
    """
    Tests para la herramienta que retorna el catálogo de layouts disponibles.
    No usa BD ni LLM.
    """

    def test_get_slide_types_returns_layouts(self):
        """
        GIVEN: nada (herramienta sin dependencias)
        WHEN: se llama a GetSlideTypesTool
        THEN: debe retornar una lista no vacía de layouts
        """
        from agents.architect import GetSlideTypesTool

        tool = GetSlideTypesTool()
        result = tool.run()

        assert "available_layouts" in result
        assert len(result["available_layouts"]) > 0
        assert "aliases" in result

    def test_get_slide_types_contains_key_layouts(self):
        """
        GIVEN: el catálogo de layouts del sistema
        WHEN: se consulta la lista de tipos
        THEN: deben estar presentes los layouts esenciales (cover_hero, two_column_text)
        """
        from agents.architect import GetSlideTypesTool

        tool = GetSlideTypesTool()
        result = tool.run()
        layouts = result["available_layouts"]

        # Verificamos que los layouts críticos existen en el catálogo
        expected_critical_layouts = ["cover_hero", "two_column"]
        for layout in expected_critical_layouts:
            assert layout in layouts, f"Layout '{layout}' must be in the catalog"
