"""
test_qa_validator_v2_artistic.py — Artistic Generation Engine v2, Phase 3.
docs/specs/artistic-generation-v2.md

Covers the AI Architect ADR's confirmed finding (docs/ai/contracts/
artistic-generation-v2-adr.md): ScoreFidelityTool's slides_context never
included canvas_elements (composition-blind for v1 AND v2 alike), and a live
test showed the only channel that did reach the judge (free-text reasoning)
carried a measurable bold-vs-safe bias (0.68 vs 0.95 for identical signals).

Tests here verify: (1) _summarize_canvas_elements()'s geometry defect check,
(2) v1 jobs are completely unaffected (same inline prompt, no
canvas_composition key), (3) v2_artistic jobs get the new seeded prompt with
canvas_composition summaries, (4) the fail-open behavior when the v2 prompt
isn't seeded.
"""
from unittest.mock import patch

import pytest

import models
from agents.qa_validator import ScoreFidelityTool, _summarize_canvas_elements


def _upsert_config(db_session, key: str, value: str):
    """Same upsert discipline as tests/test_compose_canvas.py — a blind add()
    collides once an app-boot test (tests/unit/test_footer.py) has already
    seeded this key for real via the actual seed_data()."""
    existing = db_session.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if existing:
        existing.value = value
    else:
        db_session.add(models.SystemConfig(key=key, value=value))
    db_session.flush()


# ---------------------------------------------------------------------------
# _summarize_canvas_elements
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSummarizeCanvasElements:

    def test_counts_elements_by_type(self):
        elements = [
            {"type": "text", "x": 0, "y": 0, "w": 10, "h": 10},
            {"type": "text", "x": 0, "y": 0, "w": 10, "h": 10},
            {"type": "shape", "x": 0, "y": 0, "w": 10, "h": 10},
        ]
        summary = _summarize_canvas_elements(elements)
        assert summary["element_count"] == 3
        assert summary["type_counts"] == {"text": 2, "shape": 1}

    def test_flags_element_exceeding_canvas_bounds(self):
        elements = [{"type": "shape", "x": 90, "y": 0, "w": 20, "h": 10}]  # x+w = 110
        summary = _summarize_canvas_elements(elements)
        assert summary["out_of_bounds_count"] == 1

    def test_within_bounds_element_not_flagged(self):
        elements = [{"type": "shape", "x": 50, "y": 50, "w": 20, "h": 20}]
        summary = _summarize_canvas_elements(elements)
        assert summary["out_of_bounds_count"] == 0

    def test_malformed_element_skipped_not_raised(self):
        elements = [{"type": "text", "x": "not-a-number"}, {"type": "shape", "x": 0, "y": 0, "w": 10, "h": 10}]
        summary = _summarize_canvas_elements(elements)
        assert summary["element_count"] == 2
        assert summary["out_of_bounds_count"] == 0

    def test_non_list_input_returns_empty_summary(self):
        assert _summarize_canvas_elements(None) == {"element_count": 0, "type_counts": {}, "out_of_bounds_count": 0}

    def test_line_element_without_x_y_w_h_not_a_false_positive(self):
        # line elements use x1/y1/x2/y2, not x/y/w/h — must not crash or false-flag
        elements = [{"type": "line", "x1": 0, "y1": 0, "x2": 100, "y2": 0}]
        summary = _summarize_canvas_elements(elements)
        assert summary["element_count"] == 1
        assert summary["out_of_bounds_count"] == 0


# ---------------------------------------------------------------------------
# ScoreFidelityTool — v1 unaffected, v2_artistic gets canvas_composition
# ---------------------------------------------------------------------------

def _slide(**overrides):
    defaults = dict(slide_number=1, title="S", status=models.PresentationSlideStatus.PLANNED,
                     planning_json={"art_director": {}})
    defaults.update(overrides)
    return models.PresentationSlide(**defaults)


@pytest.mark.unit
class TestScoreFidelityEngineVersionRouting:

    def test_v1_job_uses_inline_prompt_no_canvas_composition(self, mock_llm_calls, db_session, sample_brand, sample_job):
        slide = _slide(job_id=sample_job.id, planning_json={"art_director": {"reasoning": "x"}})
        db_session.add(slide)
        db_session.flush()
        mock_llm_calls["generate_json"].return_value = [
            {"slide_number": 1, "score": 0.9, "needs_rework": False, "reasoning": "fine"}
        ]

        tool = ScoreFidelityTool()
        with patch("agents.qa_validator.SessionLocal", return_value=db_session):
            tool.run(job_id=sample_job.id)

        prompt_sent = mock_llm_calls["generate_json"].call_args[0][0]
        assert "canvas_composition" not in prompt_sent
        assert "STRICT SCORING RULES" not in prompt_sent  # the v2 prompt's own marker text

    def test_v2_artistic_job_includes_canvas_composition_in_prompt(self, mock_llm_calls, db_session, sample_brand, sample_job):
        sample_job.engine_version = "v2_artistic"
        _upsert_config(db_session, "prompt_score_fidelity_v2_artistic",
                       "BRAND: {brand_context}\nSLIDES: {slides_context}\nOutput a JSON ARRAY.")
        slide = _slide(job_id=sample_job.id, planning_json={
            "art_director": {"reasoning": "bold asymmetric", "canvas_elements": [
                {"type": "text", "x": 0, "y": 0, "w": 50, "h": 10},
            ]}
        })
        db_session.add(slide)
        db_session.flush()
        mock_llm_calls["generate_json"].return_value = [
            {"slide_number": 1, "score": 0.9, "needs_rework": False, "reasoning": "fine"}
        ]

        tool = ScoreFidelityTool()
        with patch("agents.qa_validator.SessionLocal", return_value=db_session):
            tool.run(job_id=sample_job.id)

        prompt_sent = mock_llm_calls["generate_json"].call_args[0][0]
        assert "canvas_composition" in prompt_sent
        assert '"element_count": 1' in prompt_sent

    def test_v2_artistic_without_seeded_prompt_fails_open(self, mock_llm_calls, db_session, sample_brand, sample_job):
        sample_job.engine_version = "v2_artistic"
        db_session.query(models.SystemConfig).filter(
            models.SystemConfig.key == "prompt_score_fidelity_v2_artistic"
        ).delete()
        db_session.flush()
        slide = _slide(job_id=sample_job.id)
        db_session.add(slide)
        db_session.flush()

        tool = ScoreFidelityTool()
        with patch("agents.qa_validator.SessionLocal", return_value=db_session):
            result = tool.run(job_id=sample_job.id)

        assert result == []
        mock_llm_calls["generate_json"].assert_not_called()

    def test_null_engine_version_treated_as_v1(self, mock_llm_calls, db_session, sample_brand, sample_job):
        assert sample_job.engine_version is None
        slide = _slide(job_id=sample_job.id)
        db_session.add(slide)
        db_session.flush()
        mock_llm_calls["generate_json"].return_value = [
            {"slide_number": 1, "score": 0.9, "needs_rework": False, "reasoning": "fine"}
        ]

        tool = ScoreFidelityTool()
        with patch("agents.qa_validator.SessionLocal", return_value=db_session):
            tool.run(job_id=sample_job.id)

        prompt_sent = mock_llm_calls["generate_json"].call_args[0][0]
        assert "canvas_composition" not in prompt_sent
