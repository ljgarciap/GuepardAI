from schemas.presentation import ContentManifest, ContentManifestSlide, RenderManifest, PainterSlideData

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
