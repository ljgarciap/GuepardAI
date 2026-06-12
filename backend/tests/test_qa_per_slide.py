"""
Fix 1: QA retry per-slide.
Tests that ScoreFidelityTool returns List[Dict] and that the orchestrator
only resets the specific failing slides, leaving others untouched.
"""
import pytest
from unittest.mock import MagicMock, patch

import models
from agents.qa_validator import ScoreFidelityTool


# ─────────────────────────────────────────────────────
# ScoreFidelityTool return shape
# ─────────────────────────────────────────────────────

def test_score_fidelity_returns_list(mock_llm_calls, db_session, sample_job, sample_slides):
    """ScoreFidelityTool.run() must return a list, not a dict."""
    # Mark slides as PLANNED (validator only evaluates PLANNED slides)
    for s in sample_slides:
        s.status = models.PresentationSlideStatus.PLANNED
    db_session.flush()

    mock_llm_calls["generate_json"].return_value = [
        {"slide_number": s.slide_number, "score": 0.92, "needs_rework": False, "reasoning": "OK"}
        for s in sample_slides
    ]

    tool = ScoreFidelityTool()
    with patch("agents.qa_validator.SessionLocal", return_value=db_session), \
         patch.object(db_session, "close"):
        result = tool.run(job_id=sample_job.id)

    assert isinstance(result, list), "ScoreFidelityTool must return a list"
    assert len(result) == len(sample_slides)
    for item in result:
        assert "slide_number" in item
        assert "score" in item
        assert "needs_rework" in item
        assert "reasoning" in item


def test_score_fidelity_per_slide_needs_rework(mock_llm_calls, db_session, sample_job, sample_slides):
    """Only the slide flagged by the LLM should have needs_rework=True."""
    for s in sample_slides:
        s.status = models.PresentationSlideStatus.PLANNED
    db_session.flush()

    failing_slide_number = sample_slides[1].slide_number

    mock_llm_calls["generate_json"].return_value = [
        {"slide_number": sample_slides[0].slide_number, "score": 0.95, "needs_rework": False, "reasoning": "OK"},
        {"slide_number": failing_slide_number,           "score": 0.40, "needs_rework": True,  "reasoning": "Low quality image"},
        {"slide_number": sample_slides[2].slide_number, "score": 0.90, "needs_rework": False, "reasoning": "OK"},
    ]

    tool = ScoreFidelityTool()
    with patch("agents.qa_validator.SessionLocal", return_value=db_session), \
         patch.object(db_session, "close"):
        result = tool.run(job_id=sample_job.id)

    rework_slides = [r["slide_number"] for r in result if r["needs_rework"]]
    assert rework_slides == [failing_slide_number]


def test_score_fidelity_llm_failure_returns_empty_list(mock_llm_calls, db_session, sample_job, sample_slides):
    """When LLM call fails, ScoreFidelityTool must return [] (auto-pass, no slides reset)."""
    for s in sample_slides:
        s.status = models.PresentationSlideStatus.PLANNED
    db_session.flush()

    mock_llm_calls["generate_json"].side_effect = Exception("LLM unavailable")

    tool = ScoreFidelityTool()
    result = tool.run(job_id=sample_job.id)

    assert result == [], "LLM failure must return empty list (auto-pass)"


def test_score_fidelity_unparseable_response_returns_empty_list(mock_llm_calls, db_session, sample_job, sample_slides):
    """When LLM returns an unexpected shape, ScoreFidelityTool must return []."""
    for s in sample_slides:
        s.status = models.PresentationSlideStatus.PLANNED
    db_session.flush()

    mock_llm_calls["generate_json"].return_value = "not a list or dict"

    tool = ScoreFidelityTool()
    result = tool.run(job_id=sample_job.id)

    assert result == []


# ─────────────────────────────────────────────────────
# Orchestrator per-slide retry logic
# ─────────────────────────────────────────────────────

def _make_orchestrator(db_session):
    from agents.orchestrator import AgentOrchestrator
    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    orch.MAX_RETRIES = 2
    # Stub all tool calls except what we want to test
    orch.compose_layout = MagicMock()
    orch.render_pptx = MagicMock(return_value="/tmp/test.pptx")
    orch.generate_text = MagicMock(return_value="")
    return orch


def test_orchestrator_only_resets_failing_slides(
    mock_llm_calls, db_session, sample_job, sample_slides
):
    """
    When only slide_number=2 fails QA, slides 1 and 3 must remain PLANNED.
    Only slide 2 is reset to CONTENT_READY for retry.
    """
    # Set all slides to PLANNED
    for s in sample_slides:
        s.status = models.PresentationSlideStatus.PLANNED
        s.qa_retry_count = 0
        s.qa_forced = 0
    db_session.flush()

    slide_numbers = sorted([s.slide_number for s in sample_slides])
    failing_slide = slide_numbers[1]
    passing_slides = [n for n in slide_numbers if n != failing_slide]

    call_count = 0

    def mock_score_fidelity(job_id):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call: slide 2 fails
            return [
                {"slide_number": slide_numbers[0], "score": 0.95, "needs_rework": False, "reasoning": "OK"},
                {"slide_number": failing_slide,    "score": 0.30, "needs_rework": True,  "reasoning": "Bad image"},
                {"slide_number": slide_numbers[2], "score": 0.92, "needs_rework": False, "reasoning": "OK"},
            ]
        else:
            # Second call: all pass
            return [
                {"slide_number": n, "score": 0.95, "needs_rework": False, "reasoning": "OK"}
                for n in slide_numbers
            ]

    def mock_validate_brand(job_id):
        return {"status": "passed", "violations": []}

    orch = _make_orchestrator(db_session)
    orch.validate_brand = MagicMock(side_effect=mock_validate_brand)
    orch.score_fidelity = MagicMock(side_effect=mock_score_fidelity)

    with patch("agents.orchestrator.SessionLocal", return_value=db_session):
        orch.run_design_and_render(job_id=sample_job.id, req_data={}, db=db_session)

    db_session.refresh(sample_job)
    for s in sample_slides:
        db_session.refresh(s)

    # Slides that were passing must never have been reset — they should be PLANNED still
    for s in sample_slides:
        if s.slide_number in passing_slides:
            assert s.status == models.PresentationSlideStatus.PLANNED, (
                f"Slide {s.slide_number} (passing) should remain PLANNED but got {s.status}"
            )

    assert call_count == 2, "QA validator should be called twice (one fail + one pass)"


def test_orchestrator_sets_slide_qa_forced_when_retries_exhausted(
    mock_llm_calls, db_session, sample_job, sample_slides
):
    """When a slide exhausts MAX_RETRIES, qa_forced=1 is set on the slide and the job."""
    for s in sample_slides:
        s.status = models.PresentationSlideStatus.PLANNED
        s.qa_retry_count = 0
        s.qa_forced = 0
    db_session.flush()

    failing_slide_num = sample_slides[0].slide_number

    def always_fail_score(job_id):
        return [
            {"slide_number": failing_slide_num, "score": 0.20, "needs_rework": True, "reasoning": "Always fail"}
        ] + [
            {"slide_number": s.slide_number, "score": 0.95, "needs_rework": False, "reasoning": "OK"}
            for s in sample_slides[1:]
        ]

    orch = _make_orchestrator(db_session)
    orch.validate_brand = MagicMock(return_value={"status": "passed", "violations": []})
    orch.score_fidelity = MagicMock(side_effect=always_fail_score)

    with patch("agents.orchestrator.SessionLocal", return_value=db_session):
        orch.run_design_and_render(job_id=sample_job.id, req_data={}, db=db_session)

    db_session.refresh(sample_job)
    failing_slide_obj = next(s for s in sample_slides if s.slide_number == failing_slide_num)
    db_session.refresh(failing_slide_obj)

    assert failing_slide_obj.qa_forced == 1, "Slide that exhausted retries must have qa_forced=1"
    assert sample_job.qa_forced == 1, "Job must have qa_forced=1 when any slide was force-accepted"
