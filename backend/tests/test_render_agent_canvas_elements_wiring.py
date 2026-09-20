"""
test_render_agent_canvas_elements_wiring.py — canvas_elements must reach both
renderers (Synthesis Studio v2, Finding 1b).

The Art Director (art_director_service.py) writes canvas_elements into
PresentationSlide.planning_json["art_director"]["canvas_elements"] for every
slide, regardless of tier/output_format. Two independent gaps kept it from
ever reaching a renderer:
  - PPTX: RenderPPTXTool hardcoded PainterSlideData(elements=[]).
  - Premium PDF: RenderPPTXTool rebuilt a fresh ContentManifestSlide without
    passing planning_json through at all, so PremiumVisualAgent's own
    (correct) `getattr(content_slide, "planning_json", {})` always saw {}.
"""
import pytest
from unittest.mock import MagicMock, patch

import models
from agents.render_agent import RenderPPTXTool


def _make_job_and_slide(db_session, sample_brand, *, canvas_elements):
    # PainterAgencyBranding.logo_path is a required str (unrelated to this
    # fix) — the PPTX branch builds it from Brand.logo_path, which
    # sample_brand doesn't set by default.
    sample_brand.logo_path = "agency_logo.png"
    job = models.GenerationJob(brand_id=sample_brand.id, status=models.GenerationJobStatus.PENDING, prompt="Test")
    db_session.add(job)
    db_session.flush()

    slide = models.PresentationSlide(
        job_id=job.id,
        slide_number=1,
        title="Custom Canvas Slide",
        content_json={"bullets": [], "layout_type": "custom_canvas"},
        planning_json={"art_director": {"canvas_elements": canvas_elements}},
        status=models.PresentationSlideStatus.CONTENT_READY,
    )
    db_session.add(slide)
    db_session.flush()
    return job, slide


SAMPLE_ELEMENTS = [{"type": "text", "content": "Hello", "x": 10, "y": 10}]


@pytest.mark.integration
class TestPptxPathForwardsCanvasElements:

    def test_canvas_elements_reach_painter_slide_data(self, db_session, sample_brand):
        job, slide = _make_job_and_slide(db_session, sample_brand, canvas_elements=SAMPLE_ELEMENTS)

        captured = {}
        fake_painter_instance = MagicMock()
        fake_painter_instance.render_slides.side_effect = lambda manifest: captured.update(manifest=manifest)

        with patch("agents.render_agent.SessionLocal", return_value=db_session), \
             patch("agents.render_agent.GammaPainter", return_value=fake_painter_instance):
            RenderPPTXTool().run(job_id=job.id, output_format="pptx", is_premium=False)

        rendered_slide = captured["manifest"].slides[0]
        assert rendered_slide.elements == SAMPLE_ELEMENTS

    def test_no_art_director_planning_degrades_to_empty_elements(self, db_session, sample_brand):
        sample_brand.logo_path = "agency_logo.png"
        job = models.GenerationJob(brand_id=sample_brand.id, status=models.GenerationJobStatus.PENDING, prompt="Test")
        db_session.add(job)
        db_session.flush()
        slide = models.PresentationSlide(
            job_id=job.id, slide_number=1, title="No planning",
            content_json={"bullets": [], "layout_type": "composition_split"},
            status=models.PresentationSlideStatus.CONTENT_READY,
        )
        db_session.add(slide)
        db_session.flush()

        captured = {}
        fake_painter_instance = MagicMock()
        fake_painter_instance.render_slides.side_effect = lambda manifest: captured.update(manifest=manifest)

        with patch("agents.render_agent.SessionLocal", return_value=db_session), \
             patch("agents.render_agent.GammaPainter", return_value=fake_painter_instance):
            RenderPPTXTool().run(job_id=job.id, output_format="pptx", is_premium=False)

        assert captured["manifest"].slides[0].elements == []


@pytest.mark.integration
class TestPremiumPdfPathForwardsCanvasElements:

    def test_canvas_elements_reach_premium_visual_agent_via_planning_json(self, db_session, sample_brand):
        job, slide = _make_job_and_slide(db_session, sample_brand, canvas_elements=SAMPLE_ELEMENTS)

        captured = {}

        def fake_render_pdf(self, content_manifest, design_manifest, brand_dna):
            captured["content_manifest"] = content_manifest
            return "/fake/premium.pdf"

        with patch("agents.render_agent.SessionLocal", return_value=db_session), \
             patch("services.rendering.premium_visual_agent.PremiumVisualAgent.render_pdf", fake_render_pdf):
            RenderPPTXTool().run(job_id=job.id, output_format="pdf_artistic", is_premium=True)

        rendered_slide = captured["content_manifest"].slides[0]
        assert rendered_slide.planning_json["art_director"]["canvas_elements"] == SAMPLE_ELEMENTS
