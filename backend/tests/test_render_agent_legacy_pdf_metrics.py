"""
test_render_agent_legacy_pdf_metrics.py — el path PDF legacy debe reenviar
metrics/section_label/subtitle a artistic_data_grid.html.

Hallazgo (Synthesis Studio v2, sesión de elicitación 2026-09-20): el diccionario
de slide que RenderPPTXTool arma para output_format="pdf_artistic" (is_premium=False)
nunca incluía "metrics" — solo "bullets". artistic_data_grid.html itera sobre
slide.metrics para dibujar las tarjetas; sin el campo, la plantilla renderiza una
página en blanco pese a que el Redactor sí produce metrics reales. Confirmado con
una corrida de producción real, no solo con un test aislado.
"""
import pytest
from unittest.mock import patch

import models
from agents.render_agent import RenderPPTXTool


@pytest.mark.integration
class TestLegacyPdfForwardsStructuredFields:

    def test_metrics_section_label_and_subtitle_reach_the_pdf_slide_dict(self, db_session, sample_brand):
        job = models.GenerationJob(
            brand_id=sample_brand.id,
            status=models.GenerationJobStatus.PENDING,
            prompt="Test",
        )
        db_session.add(job)
        db_session.flush()

        slide = models.PresentationSlide(
            job_id=job.id,
            slide_number=1,
            title="Nordics ARR Growth",
            content_json={
                "bullets": [],
                "metrics": [{"label": "ARR Growth", "value": "34%"}, {"label": "New Logos", "value": "3"}],
                "section_label": "RESULTS",
                "subtitle": "34% YoY",
                "layout_type": "data_grid_cards",
            },
            status=models.PresentationSlideStatus.CONTENT_READY,
        )
        db_session.add(slide)
        db_session.flush()

        tool = RenderPPTXTool()
        captured = {}

        def fake_generate_pdf(job_id, slides_data, brand_dna=None):
            captured["slides_data"] = slides_data
            return "/fake/output.pdf"

        with patch("agents.render_agent.SessionLocal", return_value=db_session), \
             patch(
                 "services.rendering.artistic_pdf_service.artistic_pdf_service.generate_pdf",
                 side_effect=fake_generate_pdf,
             ):
            tool.run(job_id=job.id, output_format="pdf_artistic", is_premium=False)

        assert "slides_data" in captured, "generate_pdf was never called"
        slide_dict = captured["slides_data"][0]
        assert slide_dict["metrics"] == [{"label": "ARR Growth", "value": "34%"}, {"label": "New Logos", "value": "3"}]
        assert slide_dict["section_label"] == "RESULTS"
        assert slide_dict["subtitle"] == "34% YoY"

    def test_missing_metrics_degrades_to_empty_list_not_exception(self, db_session, sample_brand):
        job = models.GenerationJob(
            brand_id=sample_brand.id,
            status=models.GenerationJobStatus.PENDING,
            prompt="Test",
        )
        db_session.add(job)
        db_session.flush()

        slide = models.PresentationSlide(
            job_id=job.id,
            slide_number=1,
            title="No metrics here",
            content_json={"bullets": ["A bullet"], "layout_type": "composition_split"},
            status=models.PresentationSlideStatus.CONTENT_READY,
        )
        db_session.add(slide)
        db_session.flush()

        tool = RenderPPTXTool()
        captured = {}

        def fake_generate_pdf(job_id, slides_data, brand_dna=None):
            captured["slides_data"] = slides_data
            return "/fake/output.pdf"

        with patch("agents.render_agent.SessionLocal", return_value=db_session), \
             patch(
                 "services.rendering.artistic_pdf_service.artistic_pdf_service.generate_pdf",
                 side_effect=fake_generate_pdf,
             ):
            tool.run(job_id=job.id, output_format="pdf_artistic", is_premium=False)

        assert captured["slides_data"][0]["metrics"] == []
        assert captured["slides_data"][0]["subtitle"] is None
