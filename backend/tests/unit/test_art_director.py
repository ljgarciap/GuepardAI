import pytest
from unittest.mock import MagicMock, patch


def _make_mock_asset(asset_id=42):
    """Return a MagicMock BrandAsset with JSON-serializable attributes."""
    asset = MagicMock()
    asset.id = asset_id
    asset.width = 1920
    asset.height = 1080
    asset.category = "photos"
    asset.description = "Test photo asset"
    asset.local_path = f"/storage/public/brands/1/assets/test_{asset_id}.jpg"
    asset.visual_profile = {}
    return asset


def test_safe_int_id_handling():
    """Art Director must not crash when the LLM returns non-integer asset IDs."""
    from services.generation.art_director_service import plan_presentation_design

    # LLM returns a hallucinated string ID instead of a real int
    mock_decision = {
        "layout_slug": "split-right",
        "primary_asset_id": "None (custom image required)",
        "accent_asset_id": "hallucinated_string",
        "reasoning": "Test reasoning",
        "canvas_elements": [],
    }

    mock_strategy = {
        "visual_intent": "Executive",
        "grammar_type": "split",
        "suggested_keywords": ["test"],
        "metric_value": None,
    }

    mock_asset = _make_mock_asset(42)

    with (
        patch("services.generation.art_director_service.generate_json", return_value=mock_decision),
        patch("services.generation.art_director_service.ensure_brand_fonts"),
        patch("services.generation.art_director_service.get_slide_visual_strategy", return_value=mock_strategy),
        patch("services.generation.art_director_service.find_best_assets", return_value=[(mock_asset, 0.85)]),
        patch("services.assets.asset_library_service.expand_with_visual_twins", return_value=[]),
        patch("services.generation.art_director_service.generate_ai_image", return_value=None),
    ):
        db = MagicMock()

        job = MagicMock()
        job.brand_id = 1
        job.allow_ai_images = False
        db.query.return_value.get.return_value = job

        slide = MagicMock()
        slide.slide_number = 1
        slide.title = "Test Slide"
        slide.content_json = {}
        slide.layout_slug = "split"
        slide.assigned_image = None
        slide.planning_json = {}

        # slides query (filter + order_by + all) → [slide]
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [slide]
        # existing_slides and premium_patterns (filter + all) → []
        db.query.return_value.filter.return_value.all.return_value = []
        # dna_record and config queries (filter + first) → MagicMock with typed numeric attrs
        first_mock = db.query.return_value.filter.return_value.first.return_value
        first_mock.raw_vision_response = None
        first_mock.slide_width_inches = 13.33
        first_mock.slide_height_inches = 7.5
        first_mock.primary_color = "#0052A3"
        first_mock.secondary_color = "#EE1C2E"
        first_mock.primary_font = "Arial"
        first_mock.text_main_color = "#111111"
        first_mock.text_on_dark = "#FFFFFF"
        first_mock.patterns_json = None

        try:
            plan_presentation_design(db, 1)
        except Exception as e:
            pytest.fail(f"Art Director crashed on string asset IDs: {e}")
