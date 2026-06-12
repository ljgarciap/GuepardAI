"""
test_qa_verdict.py — Consistencia del veredicto del QA Judge.

El score numérico contra el threshold es la autoridad del veredicto; la flag
needs_rework del LLM es opinión auditada (solo decide como fallback sin score).
Cubre los 6 criterios de aceptación de la spec.

Spec: docs/specs/qa-judge-verdict-consistency.md
Incidente origen: prod 2026-06-11 — score=0.92 (≥0.8) + needs_rework=true
quemaba retries y podía terminar en qa_forced=1 con score aprobatorio.
"""
import os
import pytest
from unittest.mock import patch

import models
from agents.qa_validator import ScoreFidelityTool


@pytest.fixture()
def qa_job(create_test_schema):
    """Job + slide PLANNED + visual DNA commiteados (el tool abre su propia SessionLocal)."""
    from database import SessionLocal
    db = SessionLocal()

    brand = models.Brand(name=f"QAVerdictBrand_{os.urandom(3).hex()}")
    db.add(brand); db.commit()

    dna = models.BrandVisualDna(brand_id=brand.id, source_filename="qa_verdict.pptx")
    job = models.GenerationJob(
        client_name="pytest_qa_verdict", brand_id=brand.id,
        status=models.GenerationJobStatus.PROCESSING, prompt="test",
    )
    db.add_all([dna, job]); db.commit()

    slide = models.PresentationSlide(
        job_id=job.id, slide_number=1, title="Slide QA",
        layout_slug="split-right",
        status=models.PresentationSlideStatus.PLANNED,
    )
    db.add(slide); db.commit()

    yield db, job

    db.query(models.ArtDirectorDecision).filter(models.ArtDirectorDecision.job_id == job.id).delete()
    db.query(models.PresentationSlide).filter(models.PresentationSlide.job_id == job.id).delete()
    db.query(models.GenerationJob).filter(models.GenerationJob.id == job.id).delete()
    db.query(models.BrandVisualDna).filter(models.BrandVisualDna.id == dna.id).delete()
    db.query(models.Brand).filter(models.Brand.id == brand.id).delete()
    db.query(models.SystemConfig).filter(models.SystemConfig.key == "qa_fidelity_threshold").delete()
    db.commit()
    db.close()


def _run_with_llm(qa_job, llm_response):
    db, job = qa_job
    # Patch anidado sobre el mock global de conftest (mismo target, gana el interno)
    with patch("providers.llm_provider.generate_json", return_value=llm_response):
        result = ScoreFidelityTool().run(job_id=job.id)
    db.expire_all()
    decision = (
        db.query(models.ArtDirectorDecision)
        .filter(models.ArtDirectorDecision.job_id == job.id,
                models.ArtDirectorDecision.decision_type == "qa_score")
        .order_by(models.ArtDirectorDecision.id.desc())
        .first()
    )
    return result, decision


@pytest.mark.integration
class TestQAJudgeVerdict:

    def test_score_above_threshold_overrides_llm_rework_flag(self, qa_job):
        # Criterio 1 — el shape exacto del incidente de producción
        result, decision = _run_with_llm(qa_job, {
            "score": 0.92, "needs_rework": True, "reasoning": "contradictory judge",
        })
        assert result[0]["needs_rework"] is False
        assert decision.metadata_json["llm_flag_overridden"] is True
        assert decision.metadata_json["llm_needs_rework"] is True
        db, job = qa_job
        assert db.query(models.GenerationJob).get(job.id).status == models.GenerationJobStatus.QA_PASSED

    def test_score_below_threshold_overrides_llm_pass_flag(self, qa_job):
        # Criterio 2 — el score manda en ambas direcciones
        result, decision = _run_with_llm(qa_job, {
            "score": 0.5, "needs_rework": False, "reasoning": "lenient judge",
        })
        assert result[0]["needs_rework"] is True
        assert decision.metadata_json["llm_flag_overridden"] is True

    def test_missing_score_falls_back_to_llm_flag_tolerant_parse(self, qa_job):
        # Criterio 3 — flag string "true" (bool("false") is True era el bug latente)
        result, _ = _run_with_llm(qa_job, {
            "needs_rework": "true", "reasoning": "no score given",
        })
        assert result[0]["needs_rework"] is True
        assert result[0]["score"] is None

    def test_unparseable_score_without_flag_fails_open(self, qa_job):
        # Criterio 4 — nunca abortar el pipeline por JSON malformado del judge
        result, _ = _run_with_llm(qa_job, {
            "score": "high", "reasoning": "malformed",
        })
        assert result[0]["needs_rework"] is False

    def test_threshold_read_from_system_configs(self, qa_job):
        # Criterio 5 — la config de runtime gobierna el veredicto
        db, _ = qa_job
        db.add(models.SystemConfig(
            key="qa_fidelity_threshold", value="0.95", description="test override",
        ))
        db.commit()

        result, decision = _run_with_llm(qa_job, {
            "score": 0.92, "needs_rework": False, "reasoning": "passes 0.8 but not 0.95",
        })
        assert result[0]["needs_rework"] is True
        assert decision.metadata_json["threshold"] == 0.95

    def test_out_of_range_score_is_clamped(self, qa_job):
        # Criterio 6
        result, _ = _run_with_llm(qa_job, {
            "score": 4.5, "needs_rework": False, "reasoning": "judge on a 5-point scale",
        })
        assert result[0]["score"] == 1.0
        assert result[0]["needs_rework"] is False
