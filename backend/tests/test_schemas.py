import pytest

from schemas.presentation import ContentManifest, ContentManifestSlide, RenderManifest, PainterSlideData, PainterAgencyBranding

def test_content_manifest():
    slide = ContentManifestSlide(
        slide_number=1,
        title="Welcome",
        bullets=["Point 1", "Point 2"],
        layout_type="composition_hero"
    )
    manifest = ContentManifest(
        job_id=42,
        slides=[slide]
    )
    assert manifest.job_id == 42
    assert len(manifest.slides) == 1
    assert manifest.slides[0].title == "Welcome"

def test_render_manifest():
    slide_data = PainterSlideData(
        slide_number=1,
        layout_type="composition_hero",
        title="Hello",
        bullets=[],
        metric=None,
        label=None,
        tag="INTRODUCTION",
        primary_asset_path=None
    )
    manifest = RenderManifest(
        slides=[slide_data]
    )
    assert len(manifest.slides) == 1
    assert manifest.slides[0].tag == "INTRODUCTION"


@pytest.mark.unit
def test_painter_agency_branding_allows_no_logo():
    # Real pipeline failure this regresses: agents/render_agent.py and
    # services/rendering/layout_engine.py both compute logo_path as None
    # when a brand has no ingested BrandAsset with category="logos" yet —
    # a real, valid state, not an error. logo_path used to be a required
    # `str`, so Pydantic construction raised a ValidationError and crashed
    # the whole render step for that brand (confirmed live against a real
    # brand with layout grammar mined but no logo asset ingested: "Input
    # should be a valid string [type=string_type, input_value=None]").
    # painter.py's apply_branding() already treats a falsy logo_path as
    # "skip drawing the logo," so this only needed to stop crashing first.
    branding = PainterAgencyBranding(
        name="Agency", logo_path=None, client_name="Client", email="a@b.com"
    )
    assert branding.logo_path is None
