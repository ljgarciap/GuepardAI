"""
test_pipeline_resilience.py — Tests del lote de Fixes de Resiliencia.

Cubre:
  F1: feedback de QA inyectado en el prompt del Art Director en retries.
  F2: revalidación del layout_override con el asset final.
  F3: persistencia del bullet_icon (accent asset).
  F4: flag qa_forced al agotar reintentos de QA.

Spec: docs/specs/fixes-resiliencia-pipeline.md
"""
import os
import pytest
from unittest.mock import MagicMock, patch

import models

MINIMAL_ART_DIRECTOR_PROMPT = (
    "Strategy: {visual_strategy} | Colors: {primary_color}/{secondary_color} | Font: {primary_font} | "
    "Title: {slide_title} | Bullets: {bullets} | Assets: {found_assets} | History: {visual_history} | "
    "Note: {art_direction_note} | DNA: {vision_dna_json} | Patterns: {premium_patterns_json}"
)
MINIMAL_ANALYST_PROMPT = "Analyze slide {slide_title} with bullets {bullets} and context {rag_context}"


def _upsert_config(db_session, key, value):
    rec = db_session.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if rec:
        rec.value = value
    else:
        db_session.add(models.SystemConfig(key=key, value=value, description="test"))
    # autoflush=False on the test session: flush explicitly so subsequent queries
    # in the same transaction see the new/updated value.
    db_session.flush()


def _base_setup(db_session, sample_brand, sample_job, asset_w=1300, asset_h=1500):
    """Slide CONTENT_READY + asset primario apto + configs mínimas (threshold bajo)."""
    _upsert_config(db_session, "asset_score_threshold", "0.30")
    _upsert_config(db_session, "prompt_art_director_v1", MINIMAL_ART_DIRECTOR_PROMPT)
    _upsert_config(db_session, "prompt_art_director_v2", MINIMAL_ART_DIRECTOR_PROMPT)

    slide = models.PresentationSlide(
        job_id=sample_job.id,
        slide_number=1,
        title="Retail Strategy",
        status=models.PresentationSlideStatus.CONTENT_READY,
        content_json={"visual_tags": ["retail", "store"], "bullets": ["Point A"]},
    )
    db_session.add(slide)

    asset = models.BrandAsset(
        brand_id=sample_brand.id,
        file_hash="p" * 64,
        local_path="primary_photo.png",
        category="lifestyle_photos",
        description="Foto principal para tests",
        tags=["retail", "store"],
        width=asset_w,
        height=asset_h,
        is_public=0,
        embedding=None,
    )
    db_session.add(asset)
    db_session.flush()
    return slide, asset


def _run_plan(db_session, job_id, qa_feedback=None):
    from services.generation.art_director_service import plan_presentation_design
    with patch("providers.llm_provider.get_embedding", side_effect=Exception("no embeddings in tests")):
        return plan_presentation_design(db_session, job_id, is_premium=False, qa_feedback=qa_feedback)


def _get_audit_prompt(db_session, job_id):
    audit = db_session.query(models.ArtDirectorDecision).filter(
        models.ArtDirectorDecision.job_id == job_id,
        models.ArtDirectorDecision.decision_type == "layout_selection",
    ).first()
    return audit.prompt_used if audit else ""


# ─────────────────────────────────────────────────────────────────────────────
# F1 — Feedback de QA en retries
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration
class TestQAFeedbackInjection:

    def test_feedback_appears_in_art_director_prompt(self, db_session, sample_brand, sample_job):
        _base_setup(db_session, sample_brand, sample_job)
        assert _run_plan(db_session, sample_job.id, qa_feedback="Slide 1 used a competitor logo") is True

        prompt = _get_audit_prompt(db_session, sample_job.id)
        assert "PREVIOUS QA REJECTION (MUST ADDRESS IN THIS ATTEMPT)" in prompt
        assert "Slide 1 used a competitor logo" in prompt

    def test_first_attempt_has_no_feedback_block(self, db_session, sample_brand, sample_job):
        _base_setup(db_session, sample_brand, sample_job)
        assert _run_plan(db_session, sample_job.id, qa_feedback=None) is True

        prompt = _get_audit_prompt(db_session, sample_job.id)
        assert "PREVIOUS QA REJECTION" not in prompt

    def test_feedback_truncated_by_config(self, db_session, sample_brand, sample_job):
        _base_setup(db_session, sample_brand, sample_job)
        _upsert_config(db_session, "qa_feedback_max_chars", "50")

        long_feedback = ("A" * 50) + "MARKER_BEYOND_LIMIT"
        assert _run_plan(db_session, sample_job.id, qa_feedback=long_feedback) is True

        prompt = _get_audit_prompt(db_session, sample_job.id)
        assert "A" * 50 in prompt
        assert "MARKER_BEYOND_LIMIT" not in prompt

    def test_orchestrator_passes_feedback_on_retry(self):
        """El segundo intento del Architect recibe las violations del determinista como Dict[int, str]."""
        from agents.orchestrator import AgentOrchestrator
        from database import SessionLocal

        db = SessionLocal()
        job = models.GenerationJob(
            client_name="pytest_feedback_retry", brand_id=0,
            status=models.GenerationJobStatus.PROCESSING, prompt="test",
        )
        db.add(job)
        db.flush()
        slide = models.PresentationSlide(
            job_id=job.id, slide_number=1, title="Test Slide",
            status=models.PresentationSlideStatus.PLANNED,
            content_json={},
        )
        db.add(slide)
        db.commit()
        job_id = job.id

        try:
            orch = AgentOrchestrator()
            orch.compose_layout = MagicMock(return_value={"success": True})
            orch.validate_brand = MagicMock(side_effect=[
                {"status": "failed", "violations": [{"rule": "HI_RES_BACKGROUND_VIOLATION", "slide_number": 1}]},
                {"status": "passed", "violations": []},
            ])
            # score_fidelity only called on the second iteration (when brand validation passes)
            orch.score_fidelity = MagicMock(return_value=[])  # no LLM failures — List[Dict] shape
            orch.render_pptx = MagicMock(return_value=None)

            orch.run_design_and_render(job_id, {})

            assert orch.compose_layout.call_count == 2
            first_kwargs = orch.compose_layout.call_args_list[0].kwargs
            second_kwargs = orch.compose_layout.call_args_list[1].kwargs
            assert first_kwargs.get("qa_feedback") is None
            # qa_feedback is now Dict[int, str] — keyed by slide_number
            feedback = second_kwargs.get("qa_feedback", {})
            assert isinstance(feedback, dict)
            assert "HI_RES_BACKGROUND_VIOLATION" in feedback.get(1, "")
        finally:
            db.query(models.PresentationSlide).filter(models.PresentationSlide.job_id == job_id).delete()
            db.query(models.GenerationJob).filter(models.GenerationJob.id == job_id).delete()
            db.commit()
            db.close()


# ─────────────────────────────────────────────────────────────────────────────
# F2 — Revalidación tras layout_override
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration
class TestLayoutOverrideRevalidation:

    def _run_with_override(self, db_session, sample_job, mock_llm_calls, asset, override_slug, analyst_grammar="data_grid"):
        _upsert_config(db_session, "prompt_analyst_v1", MINIMAL_ANALYST_PROMPT)
        analyst_strategy = {"grammar_type": analyst_grammar, "visual_intent": "Exec",
                            "suggested_keywords": ["retail", "store"]}
        mock_llm_calls["generate_json"].return_value = {
            "primary_asset_id": asset.id,
            "suggested_layout_override": override_slug,
            "visual_reasoning": "test override",
        }
        with patch("services.generation.analyst_service.generate_json", return_value=analyst_strategy):
            return _run_plan(db_session, sample_job.id)

    def test_override_to_hi_res_rejected_for_low_res_asset(self, db_session, sample_brand, sample_job, mock_llm_calls):
        # 900px pasa el filtro para data_grid (>=800) pero NO califica para full_bleed (>=1200)
        slide, asset = _base_setup(db_session, sample_brand, sample_job, asset_w=900, asset_h=506)

        assert self._run_with_override(db_session, sample_job, mock_llm_calls, asset, "full_bleed") is True

        db_session.refresh(slide)
        assert slide.layout_slug != "full_bleed"
        assert slide.render_elements["grammar_type"] == "data_grid"

        ad = slide.planning_json["art_director"]
        assert ad["layout_override"] is None
        assert ad["layout_override_rejected"]["override"] == "full_bleed"
        assert "Resolution too low" in ad["layout_override_rejected"]["reason"]

    def test_valid_override_still_applies(self, db_session, sample_brand, sample_job, mock_llm_calls):
        # 1300×1500 califica para split (>=1200 y ratio compatible con el panel)
        slide, asset = _base_setup(db_session, sample_brand, sample_job, asset_w=1300, asset_h=1500)

        assert self._run_with_override(db_session, sample_job, mock_llm_calls, asset, "split-right") is True

        db_session.refresh(slide)
        assert slide.layout_slug == "split-right"
        assert slide.render_elements["grammar_type"] == "split-right"
        assert slide.planning_json["art_director"]["layout_override_rejected"] is None

    def test_override_without_asset_applies_unvalidated(self, db_session, sample_brand, sample_job, mock_llm_calls):
        # Sin asset asignable no hay nada que revalidar: el override se respeta
        _upsert_config(db_session, "asset_score_threshold", "0.30")
        _upsert_config(db_session, "prompt_art_director_v1", MINIMAL_ART_DIRECTOR_PROMPT)
        _upsert_config(db_session, "prompt_art_director_v2", MINIMAL_ART_DIRECTOR_PROMPT)
        _upsert_config(db_session, "prompt_analyst_v1", MINIMAL_ANALYST_PROMPT)

        slide = models.PresentationSlide(
            job_id=sample_job.id, slide_number=1, title="No assets here",
            status=models.PresentationSlideStatus.CONTENT_READY,
            content_json={"visual_tags": ["nomatch"], "bullets": []},
        )
        db_session.add(slide)
        db_session.flush()

        mock_llm_calls["generate_json"].return_value = {
            "primary_asset_id": None,
            "suggested_layout_override": "full_bleed",
            "visual_reasoning": "no asset",
        }
        analyst_strategy = {"grammar_type": "data_grid", "visual_intent": "Exec", "suggested_keywords": ["nomatch"]}
        with patch("services.generation.analyst_service.generate_json", return_value=analyst_strategy):
            assert _run_plan(db_session, sample_job.id) is True

        db_session.refresh(slide)
        assert slide.layout_slug == "full_bleed"
        assert slide.planning_json["art_director"]["layout_override_rejected"] is None


# ─────────────────────────────────────────────────────────────────────────────
# F3 — Persistencia del bullet_icon
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration
class TestBulletIconPersistence:

    def test_accent_asset_persists_as_bullet_icon(self, db_session, sample_brand, sample_job, mock_llm_calls):
        slide, primary = _base_setup(db_session, sample_brand, sample_job)

        accent = models.BrandAsset(
            brand_id=sample_brand.id,
            file_hash="a" * 64,
            local_path="accent_icon.png",
            category="design_elements",
            description="Ícono accent para tests",
            tags=["icon"],
            width=300, height=300,
            is_public=0,
            embedding=None,
        )
        db_session.add(accent)
        db_session.flush()

        mock_llm_calls["generate_json"].return_value = {
            "primary_asset_id": primary.id,
            "accent_asset_id": accent.id,
            "visual_reasoning": "with accent",
        }
        assert _run_plan(db_session, sample_job.id) is True

        db_session.refresh(slide)
        # El bug pre-existente descartaba bullet_icon al re-leer planning_json
        assert slide.planning_json["bullet_icon"] == os.path.basename(accent.local_path)
        assert slide.planning_json["art_director"]["selected_asset"] == primary.id


# ─────────────────────────────────────────────────────────────────────────────
# F4 — Flag qa_forced
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration
class TestQAForcedFlag:

    def test_forced_acceptance_sets_flag(self):
        """QA falla siempre → al agotar MAX_RETRIES el job queda marcado qa_forced=1."""
        from agents.orchestrator import AgentOrchestrator
        from database import SessionLocal

        db = SessionLocal()
        job = models.GenerationJob(
            client_name="pytest_qa_forced", brand_id=0,
            status=models.GenerationJobStatus.PROCESSING, prompt="test",
        )
        db.add(job)
        db.flush()
        # Need a real slide so the per-slide retry loop can find, increment, and force-accept it
        slide = models.PresentationSlide(
            job_id=job.id, slide_number=1, title="Test Slide",
            status=models.PresentationSlideStatus.PLANNED,
            content_json={},
        )
        db.add(slide)
        db.commit()
        job_id = job.id

        try:
            orch = AgentOrchestrator()
            orch.compose_layout = MagicMock(return_value={"success": True})
            # Deterministic QA passes; LLM judge always flags slide 1 — exhausts MAX_RETRIES
            orch.validate_brand = MagicMock(return_value={"status": "passed", "violations": []})
            orch.score_fidelity = MagicMock(return_value=[
                {"slide_number": 1, "score": 0.1, "needs_rework": True, "reasoning": "Always fails"}
            ])
            orch.render_pptx = MagicMock(return_value=None)

            orch.run_design_and_render(job_id, {})

            db.expire_all()
            refreshed = db.query(models.GenerationJob).get(job_id)
            assert refreshed.qa_forced == 1
            # MAX_RETRIES=2 with > guard → 3 compose_layout calls (iterations 1, 2, 3)
            assert orch.compose_layout.call_count == orch.MAX_RETRIES + 1
        finally:
            db.query(models.PresentationSlide).filter(models.PresentationSlide.job_id == job_id).delete()
            db.query(models.GenerationJob).filter(models.GenerationJob.id == job_id).delete()
            db.commit()
            db.close()

    def test_approved_job_keeps_flag_zero(self, db_session, sample_job):
        # Default de la columna: un job normal nunca queda marcado
        assert (sample_job.qa_forced or 0) == 0
