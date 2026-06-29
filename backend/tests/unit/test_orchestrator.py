"""
test_orchestrator.py — Unit tests for agents/orchestrator.py

Strategy: instantiate AgentOrchestrator then replace tool attributes with MagicMock
directly on the instance — cleaner than class-level patches and avoids touching
the constructor.

Tests call public orchestrator methods directly; SessionLocal is patched so no
real DB connection is required.
"""
import pytest
from unittest.mock import MagicMock, patch, call
import models


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_job():
    job = MagicMock()
    job.progress = 0
    job.current_step = ""
    job.status = None
    job.qa_forced = 0
    return job


def _make_slide(slide_number=2, qa_retry_count=0):
    slide = MagicMock()
    slide.slide_number = slide_number
    slide.qa_retry_count = qa_retry_count
    slide.qa_forced = 0
    slide.status = models.PresentationSlideStatus.PLANNED
    return slide


def _make_db(job=None, slide=None):
    """
    Minimal DB mock covering two independent query chains:
      db.query(Any).get(id)          → job  (progress/status updates)
      db.query(Any).filter().first() → slide (per-slide QA retry logic)
    """
    db = MagicMock()
    db.query.return_value.get.return_value = job
    db.query.return_value.filter.return_value.first.return_value = slide
    return db


def _make_orc_with_mocks(*, validate_brand_rv=None, score_fidelity_rv=None):
    """Factory that returns an AgentOrchestrator with all pipeline tools replaced by mocks."""
    from agents.orchestrator import AgentOrchestrator

    orc = AgentOrchestrator()
    orc.generate_text = MagicMock(return_value=MagicMock())
    orc.compose_layout = MagicMock(return_value={"success": True})
    orc.validate_brand = MagicMock(
        return_value=validate_brand_rv or {"status": "passed", "violations": []}
    )
    orc.score_fidelity = MagicMock(
        return_value=score_fidelity_rv or []
    )
    orc.render_pptx = MagicMock(return_value={"success": True, "path": "/out.pptx"})
    return orc


# ─────────────────────────────────────────────────────────────────────────────
# run_generation_pipeline
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestRunGenerationPipeline:

    def test_sets_initial_progress_before_redactor(self):
        """At the moment generate_text is called, job.progress must already be 10."""
        job = _make_job()
        db = _make_db(job=job)
        orc = _make_orc_with_mocks()

        captured = {}

        def capture_on_generate(*args, **kwargs):
            captured["progress"] = job.progress
            captured["step"] = job.current_step

        orc.generate_text = MagicMock(side_effect=capture_on_generate)

        with (
            patch("agents.orchestrator.SessionLocal", return_value=db),
            patch("utils.observability.log_performance_metric"),
        ):
            orc.run_generation_pipeline(job_id=1, req_data={})

        assert captured["progress"] == 10
        assert "Redactor" in captured["step"]

    def test_happy_path_calls_full_tool_chain(self):
        """generate_text → compose_layout → validate_brand → score_fidelity → render_pptx."""
        job = _make_job()
        db = _make_db(job=job)
        orc = _make_orc_with_mocks()

        with (
            patch("agents.orchestrator.SessionLocal", return_value=db),
            patch("utils.observability.log_performance_metric"),
        ):
            orc.run_generation_pipeline(job_id=1, req_data={})

        orc.generate_text.assert_called_once()
        orc.compose_layout.assert_called_once()
        orc.validate_brand.assert_called_once()
        orc.score_fidelity.assert_called_once()
        orc.render_pptx.assert_called_once()

    def test_interactive_mode_pauses_after_redactor(self):
        """interactive_mode=True: pipeline halts after generate_text; design/render not called."""
        job = _make_job()
        db = _make_db(job=job)
        orc = _make_orc_with_mocks()

        with (
            patch("agents.orchestrator.SessionLocal", return_value=db),
            patch("utils.observability.log_performance_metric"),
        ):
            orc.run_generation_pipeline(job_id=1, req_data={"interactive_mode": True})

        orc.generate_text.assert_called_once()
        orc.compose_layout.assert_not_called()
        orc.render_pptx.assert_not_called()
        assert job.progress == 40

    def test_exception_sets_job_status_to_error(self):
        """Unhandled exception from generate_text → job.status=ERROR, current_step has error text."""
        job = _make_job()
        db = _make_db(job=job)
        orc = _make_orc_with_mocks()
        orc.generate_text = MagicMock(side_effect=Exception("boom"))

        with (
            patch("agents.orchestrator.SessionLocal", return_value=db),
            patch("utils.observability.log_performance_metric"),
        ):
            orc.run_generation_pipeline(job_id=1, req_data={})  # must not raise

        assert job.status == models.GenerationJobStatus.ERROR
        assert "boom" in job.current_step


# ─────────────────────────────────────────────────────────────────────────────
# run_design_and_render — QA per-slide retry loop
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestRunDesignAndRender:

    def test_qa_passes_first_try_calls_render_once(self):
        """Both validators approve → loop exits after one iteration, render_pptx is called."""
        job = _make_job()
        db = _make_db(job=job)
        orc = _make_orc_with_mocks()

        orc.run_design_and_render(job_id=1, req_data={}, db=db)

        orc.compose_layout.assert_called_once()
        orc.validate_brand.assert_called_once()
        orc.score_fidelity.assert_called_once()
        orc.render_pptx.assert_called_once()

    def test_deterministic_fail_resets_slide_status_to_content_ready(self):
        """Slide that fails ValidateBrand has status reset to CONTENT_READY for re-planning."""
        slide = _make_slide(slide_number=2, qa_retry_count=0)
        job = _make_job()
        db = _make_db(job=job, slide=slide)

        orc = _make_orc_with_mocks()
        # Fail iteration 1, pass iteration 2 so the loop terminates
        orc.validate_brand = MagicMock(side_effect=[
            {"status": "failed", "violations": [
                {"rule": "LOW_RES", "slide_number": 2, "message": "px too low"}
            ]},
            {"status": "passed", "violations": []},
        ])

        orc.run_design_and_render(job_id=1, req_data={}, db=db)

        assert slide.status == models.PresentationSlideStatus.CONTENT_READY
        orc.render_pptx.assert_called_once()

    def test_slide_exhausts_retries_sets_slide_qa_forced(self):
        """Slide with qa_retry_count > MAX_RETRIES gets qa_forced=1 (accepted by force)."""
        slide = _make_slide(slide_number=2, qa_retry_count=2)  # will become 3 → > MAX_RETRIES(2)
        job = _make_job()
        db = _make_db(job=job, slide=slide)

        orc = _make_orc_with_mocks()
        orc.validate_brand = MagicMock(return_value={
            "status": "failed",
            "violations": [{"rule": "LOW_RES", "slide_number": 2, "message": "low res"}],
        })

        orc.run_design_and_render(job_id=1, req_data={}, db=db)

        assert slide.qa_forced == 1
        orc.render_pptx.assert_called_once()

    def test_all_slides_forced_sets_job_qa_forced_and_proceeds_to_render(self):
        """When every failing slide exhausts retries, job.qa_forced=1 and render still runs."""
        slide = _make_slide(slide_number=2, qa_retry_count=2)
        job = _make_job()
        db = _make_db(job=job, slide=slide)

        orc = _make_orc_with_mocks()
        orc.validate_brand = MagicMock(return_value={
            "status": "failed",
            "violations": [{"rule": "LOW_RES", "slide_number": 2, "message": "low res"}],
        })

        orc.run_design_and_render(job_id=1, req_data={}, db=db)

        assert job.qa_forced == 1
        orc.render_pptx.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# resume_generation_pipeline
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestResumeGenerationPipeline:

    def test_sets_status_processing_and_delegates_to_design_render(self):
        """On resume: job.status→PROCESSING then run_design_and_render is called with same args."""
        from agents.orchestrator import AgentOrchestrator

        job = _make_job()
        db = _make_db(job=job)
        orc = AgentOrchestrator()
        orc.run_design_and_render = MagicMock()  # prevent inner execution

        req_data = {"output_format": "pptx", "tier": "standard"}

        with (
            patch("agents.orchestrator.SessionLocal", return_value=db),
            patch("utils.observability.log_performance_metric"),
        ):
            orc.resume_generation_pipeline(job_id=1, req_data=req_data)

        assert job.status == models.GenerationJobStatus.PROCESSING
        orc.run_design_and_render.assert_called_once_with(1, req_data)
