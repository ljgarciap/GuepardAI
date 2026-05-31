import os
import tempfile
from schemas.presentation import RenderManifest, PainterSlideData, PainterAgencyBranding
from services.rendering.painter import GammaPainter

class MockBrandStyle:
    primary_color = "#FF0000"
    secondary_color = "#00FF00"
    background_color = "#FFFFFF"
    font_family = "Arial"

def test_gamma_painter_with_manifest():
    brand = MockBrandStyle()
    painter = GammaPainter(brand)
    
    agency = PainterAgencyBranding(
        name="Test Agency",
        logo_path="",
        client_name="Test Client",
        email="test@example.com"
    )
    
    slide1 = PainterSlideData(
        slide_number=1,
        layout_type="composition_hero",
        title="Hero Slide",
        bullets=["Point 1"],
        metric=None,
        label=None,
        tag="INTRO",
        primary_asset_path=None
    )
    
    slide2 = PainterSlideData(
        slide_number=2,
        layout_type="composition_split",
        title="Split Slide",
        bullets=["Split 1", "Split 2"],
        metric=None,
        label=None,
        tag="CONTENT",
        primary_asset_path=None
    )
    
    manifest = RenderManifest(
        slides=[slide1, slide2],
        logo_path=None,
        agency_branding=agency
    )
    
    painter.render_slides(manifest)
    
    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tf:
        temp_path = tf.name
        
    painter.save(temp_path)
    
    assert os.path.exists(temp_path)
    assert os.path.getsize(temp_path) > 0
    os.remove(temp_path)
