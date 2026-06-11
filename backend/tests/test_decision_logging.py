"""
test_decision_logging.py — Resiliencia de BaseAgentTool.log_decision.

Reproduce el incidente de producción del 2026-06-11: el LLM QA Judge devolvió
`reasoning` como dict (pese a que el prompt pide string), el INSERT a
art_director_decisions falló con "cannot adapt type 'dict'", y aunque el error
se capturó como no-fatal, el flush fallido envenenó la sesión y el commit
posterior del Tool tumbó el pipeline con PendingRollbackError.

Cubre: coerción de campos estructurados a string y aislamiento por SAVEPOINT
(un fallo de logging jamás invalida la transacción del Tool llamador).
"""
import pytest
from pydantic import BaseModel

import models
from agents.base import BaseAgentTool


class _NoArgs(BaseModel):
    pass


class _DummyTool(BaseAgentTool):
    name = "dummy_tool"
    description = "Tool mínima para probar log_decision."
    args_schema = _NoArgs

    def run(self, **kwargs):
        return None

    async def arun(self, **kwargs):
        return None


@pytest.mark.integration
class TestLogDecisionResilience:

    def test_dict_reasoning_is_serialized_not_fatal(self, db_session, sample_job):
        # El shape exacto que devolvió el LLM judge en producción
        structured_reasoning = {
            "strengths": ["Brand tone consistent"],
            "weaknesses": ["Slide 3 feels corporate"],
        }
        tool = _DummyTool()
        tool.log_decision(
            db=db_session,
            job_id=sample_job.id,
            decision_type="qa_score",
            summary="LLM QA Judge: score=0.92, needs_rework=True",
            reasoning=structured_reasoning,
            metadata={"score": 0.92, "needs_rework": True},
        )

        row = (
            db_session.query(models.ArtDirectorDecision)
            .filter(models.ArtDirectorDecision.job_id == sample_job.id,
                    models.ArtDirectorDecision.decision_type == "qa_score")
            .first()
        )
        assert row is not None
        assert isinstance(row.reasoning, str)
        assert "Brand tone consistent" in row.reasoning

    def test_failed_log_does_not_poison_caller_transaction(self, db_session, sample_job):
        # Cambio pendiente del Tool llamador ANTES del log (como hace qa_validator)
        sample_job.status = models.GenerationJobStatus.QA_FAILED

        tool = _DummyTool()
        # metadata con un objeto no serializable a JSONB → el flush del savepoint falla
        tool.log_decision(
            db=db_session,
            job_id=sample_job.id,
            decision_type="qa_score",
            summary="poisoned metadata",
            reasoning="r",
            metadata={"bad": object()},
        )

        # La sesión sigue usable y el cambio del llamador sobrevive al fallo
        db_session.flush()
        refreshed = db_session.query(models.GenerationJob).get(sample_job.id)
        assert refreshed.status == models.GenerationJobStatus.QA_FAILED
        # El INSERT fallido no quedó a medias
        bad_rows = (
            db_session.query(models.ArtDirectorDecision)
            .filter(models.ArtDirectorDecision.summary == "poisoned metadata")
            .count()
        )
        assert bad_rows == 0
