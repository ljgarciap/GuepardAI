"""
test_redactor.py — Unit tests for agents/redactor.py

Covers SearchKnowledgeTool, SlideContentTool, and GenerateTextTool.
All DB, RAG, and LLM calls are mocked. Tests call tool.run() directly to
bypass the BaseAgentTool.__call__ wrapper (Pydantic validation + PerformanceMetric).
"""
import pytest
from unittest.mock import MagicMock, patch
import models


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_db(*, job=None, cfg=None):
    """Minimal DB mock covering GenerationJob.get() and SystemConfig.filter().first()."""
    db = MagicMock()
    db.query.return_value.get.return_value = job
    db.query.return_value.filter.return_value.first.return_value = cfg
    return db


def _make_cfg(key="prompt_slide_content_v2", value="Title: {slide_title}"):
    cfg = MagicMock()
    cfg.key = key
    cfg.value = value
    return cfg


def _slide_content_kwargs(**overrides):
    base = {
        "job_id": 1,
        "idx": 0,
        "slide_title": "Innovation Trends",
        "section_label": "STRATEGY",
        "layout_type": "composition_split",
        "knowledge_source": "brand.pptx",
        "brand_id": 1,
        "brand_name": "Acme Corp",
        "region": "Global",
        "strategic_context": "",
    }
    return {**base, **overrides}


# ─────────────────────────────────────────────────────────────────────────────
# SearchKnowledgeTool
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestSearchKnowledgeTool:

    def test_delegates_to_search_rag_with_same_args(self):
        """run() is a thin pass-through: args forwarded unchanged, return value propagated."""
        from agents.redactor import SearchKnowledgeTool

        with patch("agents.redactor.search_rag", return_value="RAG results") as mock_rag:
            result = SearchKnowledgeTool().run(
                query="digital transformation",
                knowledge_source="brand.pptx",
                k=10,
                brand_id=42,
            )

        mock_rag.assert_called_once_with(
            query="digital transformation",
            knowledge_source="brand.pptx",
            k=10,
            brand_id=42,
        )
        assert result == "RAG results"


# ─────────────────────────────────────────────────────────────────────────────
# SlideContentTool
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestSlideContentTool:

    def test_no_config_returns_default_dict_without_calling_llm(self):
        """When neither prompt_slide_content_v2 nor v1 exists, returns empty skeleton
        (no bullets, no subtitle) and does NOT call generate_json."""
        from agents.redactor import SlideContentTool

        db = _make_db(cfg=None)

        with (
            patch("agents.redactor.SessionLocal", return_value=db),
            patch("agents.redactor.search_rag", return_value="some rag"),
            patch("agents.redactor.generate_json") as mock_llm,
        ):
            idx, content = SlideContentTool().run(**_slide_content_kwargs(idx=3))

        mock_llm.assert_not_called()
        assert idx == 3
        assert content["title"] == "Innovation Trends"
        assert content["bullets"] == []

    def test_with_config_calls_generate_json_and_returns_content(self):
        """When config exists, generate_json is called and its response is merged into output."""
        from agents.redactor import SlideContentTool

        cfg = _make_cfg(
            value="Title: {slide_title}, RAG: {rag_context}, brand: {brand_name}, "
                  "lang: {target_lang}, section: {section_label}, "
                  "layout: {layout_type}, context: {strategic_context}"
        )
        db = _make_db(cfg=cfg)
        llm_response = {"bullets": ["Point A", "Point B"], "subtitle": "Sub-heading"}

        with (
            patch("agents.redactor.SessionLocal", return_value=db),
            patch("agents.redactor.search_rag", return_value="rag context text"),
            patch("agents.redactor.generate_json", return_value=llm_response),
            patch.object(__import__("agents.redactor", fromlist=["SlideContentTool"]).SlideContentTool, "log_decision"),
        ):
            idx, content = SlideContentTool().run(**_slide_content_kwargs(idx=1))

        assert idx == 1
        assert content["bullets"] == ["Point A", "Point B"]
        assert content["subtitle"] == "Sub-heading"
        assert content["title"] == "Innovation Trends"

    def test_llm_failure_returns_empty_bullets_without_raising(self):
        """LLM exception is caught (non-fatal) — empty bullets are returned, no crash."""
        from agents.redactor import SlideContentTool

        cfg = _make_cfg(
            value="Title: {slide_title}, RAG: {rag_context}, brand: {brand_name}, "
                  "lang: {target_lang}, section: {section_label}, "
                  "layout: {layout_type}, context: {strategic_context}"
        )
        db = _make_db(cfg=cfg)

        with (
            patch("agents.redactor.SessionLocal", return_value=db),
            patch("agents.redactor.search_rag", return_value="rag"),
            patch("agents.redactor.generate_json", side_effect=Exception("timeout")),
            patch.object(__import__("agents.redactor", fromlist=["SlideContentTool"]).SlideContentTool, "log_decision"),
        ):
            try:
                idx, content = SlideContentTool().run(**_slide_content_kwargs(idx=2))
            except Exception as exc:
                pytest.fail(f"SlideContentTool raised unexpectedly on LLM failure: {exc}")

        assert idx == 2
        assert content["bullets"] == []

    def test_returns_idx_as_first_element_of_tuple(self):
        """Return value is always (idx, dict) where idx matches the arg passed in."""
        from agents.redactor import SlideContentTool

        db = _make_db(cfg=None)

        with (
            patch("agents.redactor.SessionLocal", return_value=db),
            patch("agents.redactor.search_rag", return_value=""),
        ):
            result = SlideContentTool().run(**_slide_content_kwargs(idx=7))

        assert isinstance(result, tuple)
        assert result[0] == 7


# ─────────────────────────────────────────────────────────────────────────────
# GenerateTextTool
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGenerateTextTool:

    def _base_kwargs(self):
        return {
            "job_id": 1,
            "prompt": "Create a deck about AI trends",
            "style_filename": "brand.pptx",
            "knowledge_filename": "knowledge.pptx",
            "region": "Global",
            "allow_ai_images": False,
        }

    def test_sets_status_synthesizing_then_content_ready(self):
        """job.status transitions: SYNTHESIZING_CONTENT (before synthesize) → CONTENT_READY (after)."""
        from agents.redactor import GenerateTextTool

        job = MagicMock()
        db = _make_db(job=job)

        statuses_at_commit = []
        db.commit.side_effect = lambda: statuses_at_commit.append(job.status)

        manifest = MagicMock()
        manifest.slides = [MagicMock(), MagicMock()]

        with (
            patch("agents.redactor.SessionLocal", return_value=db),
            patch("agents.redactor.synthesize_presentation_outline", return_value=manifest),
            patch.object(GenerateTextTool, "log_decision"),
        ):
            GenerateTextTool().run(**self._base_kwargs())

        # First commit → SYNTHESIZING_CONTENT; last commit → CONTENT_READY
        assert statuses_at_commit[0] == models.GenerationJobStatus.SYNTHESIZING_CONTENT
        assert statuses_at_commit[-1] == models.GenerationJobStatus.CONTENT_READY

    def test_job_not_found_still_calls_synthesize(self):
        """Even when job is None, synthesize_presentation_outline is still invoked."""
        from agents.redactor import GenerateTextTool

        db = _make_db(job=None)
        manifest = MagicMock()
        manifest.slides = []

        with (
            patch("agents.redactor.SessionLocal", return_value=db),
            patch("agents.redactor.synthesize_presentation_outline", return_value=manifest) as mock_synth,
            patch.object(GenerateTextTool, "log_decision"),
        ):
            GenerateTextTool().run(**self._base_kwargs())

        mock_synth.assert_called_once()

    def test_log_decision_called_with_content_synthesis_type_and_slide_count(self):
        """log_decision is called with decision_type='content_synthesis' and the summary
        includes the number of generated slides."""
        from agents.redactor import GenerateTextTool

        job = MagicMock()
        db = _make_db(job=job)

        manifest = MagicMock()
        manifest.slides = [MagicMock(), MagicMock(), MagicMock()]

        with (
            patch("agents.redactor.SessionLocal", return_value=db),
            patch("agents.redactor.synthesize_presentation_outline", return_value=manifest),
            patch.object(GenerateTextTool, "log_decision") as mock_log,
        ):
            GenerateTextTool().run(**self._base_kwargs())

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["decision_type"] == "content_synthesis"
        assert "3" in call_kwargs["summary"]
