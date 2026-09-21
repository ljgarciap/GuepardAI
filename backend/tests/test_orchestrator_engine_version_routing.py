"""
test_orchestrator_engine_version_routing.py — Artistic Generation Engine v2.
docs/specs/artistic-generation-v2.md

The entire integration surface between v1 and v2_artistic is one branch in
AgentOrchestrator.run_design_and_render() — this is the only place that
branch is meant to exist, so it's tested in isolation with every other tool
call (compose_layout/compose_canvas/validate_brand/score_fidelity/render_pptx)
mocked out.
"""
from unittest.mock import MagicMock

import pytest

import models
from agents.orchestrator import AgentOrchestrator


def _orchestrator_with_mocked_tools():
    orch = AgentOrchestrator()
    orch.compose_layout = MagicMock()
    orch.compose_canvas = MagicMock()
    orch.validate_brand = MagicMock(return_value={"status": "passed", "violations": []})
    orch.score_fidelity = MagicMock(return_value=[])
    orch.render_pptx = MagicMock()
    return orch


@pytest.mark.unit
class TestEngineVersionRouting:

    def test_v2_artistic_calls_compose_canvas_not_compose_layout(self, db_session, sample_brand, sample_job):
        sample_job.engine_version = "v2_artistic"
        db_session.flush()

        orch = _orchestrator_with_mocked_tools()
        orch.run_design_and_render(sample_job.id, {}, db=db_session)

        orch.compose_canvas.assert_called_once()
        orch.compose_layout.assert_not_called()

    def test_null_engine_version_calls_compose_layout_not_compose_canvas(self, db_session, sample_brand, sample_job):
        assert sample_job.engine_version is None  # default, no migration/backfill needed

        orch = _orchestrator_with_mocked_tools()
        orch.run_design_and_render(sample_job.id, {}, db=db_session)

        orch.compose_layout.assert_called_once()
        orch.compose_canvas.assert_not_called()

    def test_explicit_v1_calls_compose_layout(self, db_session, sample_brand, sample_job):
        sample_job.engine_version = "v1"
        db_session.flush()

        orch = _orchestrator_with_mocked_tools()
        orch.run_design_and_render(sample_job.id, {}, db=db_session)

        orch.compose_layout.assert_called_once()
        orch.compose_canvas.assert_not_called()

    def test_v2_artistic_passes_job_id_and_qa_feedback(self, db_session, sample_brand, sample_job):
        sample_job.engine_version = "v2_artistic"
        db_session.flush()

        orch = _orchestrator_with_mocked_tools()
        orch.run_design_and_render(sample_job.id, {}, db=db_session)

        _, kwargs = orch.compose_canvas.call_args
        assert kwargs["job_id"] == sample_job.id
        assert kwargs["qa_feedback"] is None  # first iteration, no prior QA rejection
