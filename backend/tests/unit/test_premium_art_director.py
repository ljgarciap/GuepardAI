import json
import pytest
from unittest.mock import MagicMock


def _make_director():
    from services.generation.decoupled_art_director import PremiumArtDirector
    db = MagicMock()
    return PremiumArtDirector(db=db, job_id=1, uploads_dir="/tmp")


def test_generate_premium_geometry_returns_valid_json():
    director = _make_director()
    result = director._generate_premium_geometry(
        title="Test Slide",
        grammar_type="split",
        design_system={},
        assigned_image="test.jpg",
        slide_number=1
    )
    geometry = json.loads(result)
    assert "glass_panels" in geometry
    assert isinstance(geometry["glass_panels"], list)
    assert len(geometry["glass_panels"]) > 0
    assert "image_treatment" in geometry


def test_generate_premium_geometry_is_synchronous():
    import inspect
    from services.generation.decoupled_art_director import PremiumArtDirector
    assert not inspect.iscoroutinefunction(PremiumArtDirector._generate_premium_geometry)


def test_enrich_design_assigns_geometry_to_all_slides():
    from services.generation.decoupled_art_director import PremiumArtDirector
    from schemas.presentation import DesignManifest, DesignManifestSlide, ContentManifest, ContentManifestSlide

    director = _make_director()

    slides_design = [
        DesignManifestSlide(slide_number=1, layout_type="split", primary_asset_path="img1.jpg"),
        DesignManifestSlide(slide_number=2, layout_type="hero",  primary_asset_path="img2.jpg"),
    ]
    slides_content = [
        ContentManifestSlide(slide_number=1, title="Slide One",  layout_type="split", bullets=[]),
        ContentManifestSlide(slide_number=2, title="Slide Two",  layout_type="hero",  bullets=[]),
    ]
    base_manifest    = DesignManifest(job_id=1, slides=slides_design,   theme={})
    content_manifest = ContentManifest(job_id=1, slides=slides_content, theme={})

    result = director.enrich_design(base_manifest, content_manifest, design_system={})

    for slide in result.slides:
        assert slide.background_asset_path is not None
        geometry = json.loads(slide.background_asset_path)
        assert "glass_panels" in geometry


def test_vision_layout_engine_does_not_exist():
    import importlib, sys
    with pytest.raises((ImportError, ModuleNotFoundError)):
        importlib.import_module("services.rendering.vision_layout_engine")
