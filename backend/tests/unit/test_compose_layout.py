"""
test_compose_layout.py — Unit tests for ComposeLayoutTool and GetSlideTypesTool.

All DB and art-director service calls are mocked.
Tests call tool.run() directly to bypass the BaseAgentTool.__call__ wrapper.
"""
import pytest
from unittest.mock import MagicMock, patch
import models


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_slide(number=1, layout="hero", image=None, planning_json=None):
    slide = MagicMock()
    slide.slide_number = number
    slide.layout_slug = layout
    slide.assigned_image = image
    slide.planning_json = planning_json or {"art_director": {"reasoning": "Mock reasoning"}}
    slide.content_json = {}
    return slide


def _make_db(job=None, planned_slides=None):
    """
    Minimal DB mock for the non-premium ComposeLayoutTool path.
    Only two query chains are needed:
      db.query(GenerationJob).get(job_id) → job
      db.query(PresentationSlide).filter(...).all() → planned_slides
    """
    db = MagicMock()
    db.query.return_value.get.return_value = job
    db.query.return_value.filter.return_value.all.return_value = planned_slides or []
    return db


# ─────────────────────────────────────────────────────────────────────────────
# GetSlideTypesTool — pure function, no DB
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGetSlideTypesTool:

    def test_returns_all_grammar_geometries(self):
        """Result contains every layout key from GRAMMAR_GEOMETRIES and the alias map."""
        from agents.architect import GetSlideTypesTool
        from services.ingestion.brand_composition_dna import GRAMMAR_GEOMETRIES, SLUG_ALIASES

        result = GetSlideTypesTool().run()

        assert "available_layouts" in result
        assert "aliases" in result
        assert set(result["available_layouts"]) == set(GRAMMAR_GEOMETRIES.keys())
        assert result["aliases"] == SLUG_ALIASES

    def test_no_db_access_required(self):
        """GetSlideTypesTool must not open a DB session — it reads static data only."""
        from agents.architect import GetSlideTypesTool

        with patch("agents.architect.SessionLocal") as mock_session:
            GetSlideTypesTool().run()

        mock_session.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# ComposeLayoutTool
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestComposeLayoutTool:

    def test_job_not_found_still_delegates_to_art_director(self):
        """When job doesn't exist there is no status update, but plan_presentation_design
        is still called — the service owns the guard for missing jobs."""
        from agents.architect import ComposeLayoutTool

        db = _make_db(job=None)

        with (
            patch("agents.architect.SessionLocal", return_value=db),
            patch("agents.architect.plan_presentation_design", return_value=False) as mock_plan,
        ):
            result = ComposeLayoutTool().run(job_id=999)

        mock_plan.assert_called_once_with(db, 999, is_premium=False, qa_feedback=None)
        assert result == {"success": False, "job_id": 999}
        db.close.assert_called_once()

    def test_success_updates_job_status_to_design_planned(self):
        """Happy path: job.status transitions PLANNING_DESIGN → DESIGN_PLANNED."""
        from agents.architect import ComposeLayoutTool

        job = MagicMock()
        job.brand_id = 1
        db = _make_db(job=job)

        with (
            patch("agents.architect.SessionLocal", return_value=db),
            patch("agents.architect.plan_presentation_design", return_value=True),
        ):
            result = ComposeLayoutTool().run(job_id=1)

        assert job.status == models.GenerationJobStatus.DESIGN_PLANNED
        assert "Layout and images" in job.current_step
        assert result == {"success": True, "job_id": 1}
        db.close.assert_called_once()

    def test_qa_feedback_dict_forwarded_unchanged(self):
        """qa_feedback is passed through to plan_presentation_design exactly as received."""
        from agents.architect import ComposeLayoutTool

        qa_feedback = {1: "image resolution too low", 3: "layout mismatch"}
        job = MagicMock()
        db = _make_db(job=job)

        with (
            patch("agents.architect.SessionLocal", return_value=db),
            patch("agents.architect.plan_presentation_design", return_value=True) as mock_plan,
        ):
            ComposeLayoutTool().run(job_id=2, qa_feedback=qa_feedback)

        _args, call_kwargs = mock_plan.call_args
        assert call_kwargs["qa_feedback"] == qa_feedback

    def test_premium_path_calls_premium_art_director(self):
        """is_premium=True: PremiumArtDirector.enrich_design is called after standard plan."""
        from agents.architect import ComposeLayoutTool

        job = MagicMock()
        job.brand_id = 1

        db = MagicMock()
        db.query.return_value.get.return_value = job
        # BrandVisualDna query → None (code uses getattr fallbacks)
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        # PresentationSlide ordered query (content/design manifest build) → []
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
        # PresentationSlide PLANNED filter (log_decision phase) → []
        db.query.return_value.filter.return_value.all.return_value = []

        mock_art_director = MagicMock()
        mock_art_director.enrich_design.return_value = MagicMock(slides=[])
        fake_decoupled_module = MagicMock()
        fake_decoupled_module.PremiumArtDirector.return_value = mock_art_director

        fake_schemas_module = MagicMock()

        with (
            patch("agents.architect.SessionLocal", return_value=db),
            patch("agents.architect.plan_presentation_design", return_value=True),
            patch.dict("sys.modules", {
                "services.generation.decoupled_art_director": fake_decoupled_module,
                "schemas.presentation": fake_schemas_module,
            }),
            patch("os.path.exists", return_value=True),
        ):
            result = ComposeLayoutTool().run(job_id=1, is_premium=True)

        mock_art_director.enrich_design.assert_called_once()
        assert result == {"success": True, "job_id": 1}

    def test_log_decision_called_once_per_planned_slide(self):
        """After a successful layout pass, one 'layout' decision is logged per PLANNED slide."""
        from agents.architect import ComposeLayoutTool

        slides = [
            _make_slide(1, "hero", image="42"),
            _make_slide(2, "split", image=None, planning_json={}),
        ]
        db = _make_db(job=MagicMock(), planned_slides=slides)

        with (
            patch("agents.architect.SessionLocal", return_value=db),
            patch("agents.architect.plan_presentation_design", return_value=True),
            patch.object(ComposeLayoutTool, "log_decision") as mock_log,
        ):
            ComposeLayoutTool().run(job_id=3)

        assert mock_log.call_count == 2
        logged_types = [c.kwargs["decision_type"] for c in mock_log.call_args_list]
        assert all(t == "layout" for t in logged_types)
        logged_slides = [c.kwargs["slide_number"] for c in mock_log.call_args_list]
        assert logged_slides == [1, 2]
