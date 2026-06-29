"""
test_render_agent.py — Unit tests for RenderPPTXTool.

All DB, filesystem, and rendering calls are mocked.
Tests call tool.run() directly to bypass the BaseAgentTool.__call__ wrapper
(which writes PerformanceMetrics to the DB and is tested separately).
"""
import pytest
from unittest.mock import MagicMock, patch, call
import models


# ─────────────────────────────────────────────────────────────────────────────
# Test helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_job(brand_id=1):
    job = MagicMock()
    job.brand_id = brand_id
    job.progress = 0
    job.current_step = ""
    job.pptx_path = None
    job.status = None
    return job


def _make_dna():
    dna = MagicMock()
    dna.primary_color = "#0052A3"
    dna.secondary_color = "#EE1C2E"
    dna.primary_font = "Arial"
    return dna


def _make_brand(name="TestBrand"):
    brand = MagicMock()
    brand.name = name
    brand.logo_path = f"/storage/brands/1/assets/{name.lower()}_logo.png"
    return brand


def _make_db(*, job_obj, dna_obj, slides=None, logos=None, brand_obj=None):
    """
    MagicMock DB session wired per-model so the same db.query() dispatcher
    returns the right object for GenerationJob, BrandVisualDna, etc.
    """
    db = MagicMock()
    slides = slides or []
    logos = logos or []
    brand = brand_obj or _make_brand()

    def _query(model):
        q = MagicMock()
        if model is models.GenerationJob:
            q.get.return_value = job_obj
        elif model is models.BrandVisualDna:
            q.filter.return_value.order_by.return_value.first.return_value = dna_obj
        elif model is models.PresentationSlide:
            q.filter.return_value.order_by.return_value.all.return_value = slides
        elif model is models.BrandAsset:
            q.filter.return_value.all.return_value = logos
            q.get.return_value = None
        elif model is models.Brand:
            q.get.return_value = brand
        else:
            # SystemConfig, FooterConfig → None (code uses safe defaults)
            q.filter.return_value.first.return_value = None
            q.get.return_value = None
        return q

    db.query.side_effect = _query
    return db


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestRenderPPTXTool:

    def test_job_not_found_returns_error_dict(self):
        """When the job does not exist, run() returns error without crashing."""
        from agents.render_agent import RenderPPTXTool

        db = _make_db(job_obj=None, dna_obj=None)

        with patch("agents.render_agent.SessionLocal", return_value=db):
            result = RenderPPTXTool().run(job_id=999)

        assert result == {"error": "Job not found"}
        db.close.assert_called_once()

    def test_pptx_progress_set_to_80_before_render(self):
        """job.progress must reach 80 and Phase 3 step must be set before GammaPainter runs."""
        from agents.render_agent import RenderPPTXTool

        job = _make_job()
        db = _make_db(job_obj=job, dna_obj=_make_dna())

        progress_at_render_time = {}

        def capture_progress(*_args, **_kwargs):
            progress_at_render_time["progress"] = job.progress
            progress_at_render_time["step"] = job.current_step
            return MagicMock()

        mock_painter = MagicMock()
        mock_painter.render_slides.side_effect = capture_progress

        with (
            patch("agents.render_agent.SessionLocal", return_value=db),
            patch("agents.render_agent.GammaPainter", return_value=mock_painter),
            patch("services.core.storage_service.brand_assets_dir", return_value="/storage/brands/1/assets"),
            patch("services.core.storage_service.job_dir", return_value="/storage/jobs/1"),
            patch("services.core.storage_service.to_relative", return_value="jobs/1/Portfolio.pptx"),
        ):
            RenderPPTXTool().run(job_id=1)

        assert progress_at_render_time["progress"] == 80
        assert "Phase 3/3" in progress_at_render_time["step"]

    def test_pptx_happy_path_uses_gamma_painter_and_returns_success(self):
        """Successful PPTX render: GammaPainter(dna) called, render_slides + save called."""
        from agents.render_agent import RenderPPTXTool

        job = _make_job()
        dna = _make_dna()
        db = _make_db(job_obj=job, dna_obj=dna)
        mock_painter = MagicMock()

        with (
            patch("agents.render_agent.SessionLocal", return_value=db),
            patch("agents.render_agent.GammaPainter", return_value=mock_painter) as MockPainter,
            patch("services.core.storage_service.brand_assets_dir", return_value="/storage/brands/1/assets"),
            patch("services.core.storage_service.job_dir", return_value="/storage/jobs/1"),
            patch("services.core.storage_service.to_relative", return_value="jobs/1/Portfolio.pptx"),
        ):
            result = RenderPPTXTool().run(job_id=1)

        MockPainter.assert_called_once_with(dna)
        mock_painter.render_slides.assert_called_once()
        mock_painter.save.assert_called_once()
        assert result["success"] is True
        assert "path" in result
        assert job.status == models.GenerationJobStatus.COMPLETED
        assert job.progress == 100
        assert job.current_step == "Portfolio ready."

    def test_pdf_artistic_standard_delegates_to_pdf_service(self):
        """output_format='pdf_artistic' (non-premium) calls artistic_pdf_service.generate_pdf.

        artistic_pdf_service imports weasyprint which needs GTK native libs.
        We mock the entire module in sys.modules so the import inside run()
        never touches the real file.
        """
        from agents.render_agent import RenderPPTXTool

        job = _make_job()
        dna = _make_dna()
        db = _make_db(job_obj=job, dna_obj=dna)

        mock_pdf_svc = MagicMock()
        mock_pdf_svc.generate_pdf.return_value = "/storage/jobs/1/output.pdf"
        fake_pdf_module = MagicMock()
        fake_pdf_module.artistic_pdf_service = mock_pdf_svc

        with (
            patch("agents.render_agent.SessionLocal", return_value=db),
            patch("services.core.storage_service.brand_assets_dir", return_value="/storage/brands/1/assets"),
            patch.dict("sys.modules", {"services.rendering.artistic_pdf_service": fake_pdf_module}),
        ):
            result = RenderPPTXTool().run(job_id=1, output_format="pdf_artistic", is_premium=False)

        mock_pdf_svc.generate_pdf.assert_called_once()
        assert result["success"] is True
        assert job.status == models.GenerationJobStatus.COMPLETED

    def test_pdf_artistic_missing_dna_uses_fallback_color_without_crash(self):
        """When BrandVisualDna is absent (dna=None), the PDF path uses hasattr guard (#002D62)."""
        from agents.render_agent import RenderPPTXTool

        job = _make_job()
        db = _make_db(job_obj=job, dna_obj=None)

        mock_pdf_svc = MagicMock()
        mock_pdf_svc.generate_pdf.return_value = "/storage/jobs/1/output.pdf"
        fake_pdf_module = MagicMock()
        fake_pdf_module.artistic_pdf_service = mock_pdf_svc

        with (
            patch("agents.render_agent.SessionLocal", return_value=db),
            patch("services.core.storage_service.brand_assets_dir", return_value="/storage/brands/1/assets"),
            patch.dict("sys.modules", {"services.rendering.artistic_pdf_service": fake_pdf_module}),
        ):
            try:
                result = RenderPPTXTool().run(job_id=1, output_format="pdf_artistic")
            except Exception as exc:
                pytest.fail(f"RenderPPTXTool crashed with dna=None: {exc}")

        mock_pdf_svc.generate_pdf.assert_called_once()
        assert result["success"] is True
