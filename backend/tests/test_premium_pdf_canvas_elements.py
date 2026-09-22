"""
test_premium_pdf_canvas_elements.py — premium_pdf.html's canvas_elements
rendering (Synthesis Studio v2, Finding 1b).

Real Art Director output (prompt_art_director_v3) routinely includes shape,
decorator, line and gradient_overlay elements — types the template silently
dropped before this fix (only text/image/typo_substitution had a branch,
across all 3 pattern_type sections, all three now sharing one macro so they
can't drift apart again). Also covers the real bug found while writing this:
Jinja's own |float/|int filters don't protect against a genuinely missing
key (Undefined raises UndefinedError, which they don't catch) — the |num
filter registered for this exists specifically to survive that.
"""
import pytest

from services.rendering.artistic_pdf_service import ArtisticPDFService


def _base_slide(**overrides):
    slide = {
        "pattern_type": "editorial_split",
        "title": "Test", "subtitle": "", "bullets": [], "section_label": "TEST",
        "is_footer_enabled": False, "is_dark_left": True, "is_dark_right": False,
        "hero_image": None, "accent_image": None, "logo_image": None,
        "footer_logo_light": None, "footer_logo_dark": None, "footer_logo": None,
        "footer_text": "", "footer_disclaimer": "",
    }
    slide.update(overrides)
    return slide


def _render(slide):
    svc = ArtisticPDFService(templates_dir="templates")
    template = svc.env.get_template("premium_pdf.html")
    return template.render(
        slides=[slide], primary_color="#0052A3", secondary_color="#E31837",
        background_color="#FFFFFF", text_main_color="#111111", primary_font="Arial",
        agency_logo="", patterns=[], evaluation={},
    )


@pytest.mark.unit
class TestCanvasElementRendering:

    def test_renders_every_real_production_element_type_without_raising(self):
        html = _render(_base_slide(canvas_elements=[
            {"h": 55, "w": 18, "x": 15, "y": 35, "type": "shape", "color": "#2E8B57",
             "shape": "rectangle", "radius": 8, "opacity": 0.15},
            {"x": 50, "y": 55, "size": 45, "type": "shape", "color": "rgba(46, 139, 87, 0.08)",
             "shape": "circle", "border": "3px solid rgba(46, 139, 87, 0.3)"},
            {"x1": 40, "x2": 75, "y1": 40, "y2": 55, "type": "line", "stroke": "#2E8B57",
             "opacity": 0.6, "strokeWidth": 3},
            {"h": 100, "w": 100, "x": 0, "y": 0, "type": "gradient_overlay", "z_index": 1,
             "gradient": "linear-gradient(135deg, rgba(0, 56, 101, 0.7) 0%, rgba(0, 83, 159, 0.4) 100%)"},
            {"x": 60, "y": 32, "size": 22, "type": "text", "color": "#FFFFFF", "content": "Phase 1"},
            {"h": 0.4, "w": 55, "x": 8, "y": 50, "type": "decorator", "color": "#2E8B57"},
            {"type": "image", "path": "data:image/jpeg;base64,AAAA", "x": 10, "y": 10, "w": 20, "h": 20},
        ]))
        assert "linear-gradient(135deg" in html
        assert "border-radius: 50%" in html
        assert "Phase 1" in html

    def test_missing_optional_fields_do_not_crash_the_render(self):
        # Every field beyond "type" is optional in real Art Director output —
        # this is exactly the case Jinja's own |float/|int silently crashed on
        # (UndefinedError instead of the ValueError/TypeError they catch).
        html = _render(_base_slide(canvas_elements=[
            {"type": "shape"},
            {"type": "decorator"},
            {"type": "line"},
            {"type": "gradient_overlay"},
            {"type": "text"},
        ]))
        assert "canvas-element" in html

    def test_unrecognized_element_type_is_silently_skipped(self):
        html = _render(_base_slide(canvas_elements=[
            {"type": "some_future_type", "x": 1, "y": 2},
        ]))
        assert "some_future_type" not in html

    def test_circle_position_is_center_based_like_the_pptx_renderer(self):
        html = _render(_base_slide(canvas_elements=[
            {"x": 50, "y": 50, "size": 20, "type": "shape", "shape": "circle", "color": "#000"},
        ]))
        # x/y (50) minus half the size (10) -> left/top should read 40, not 50.
        assert "left: 40.0%" in html or "left: 40%" in html

    def test_applies_all_three_pattern_type_branches(self):
        # The macro is shared across full_bleed_hero / data_cards_brand_grid /
        # editorial_split (default) — confirm all three actually call it.
        for pattern_type in ("full_bleed_hero", "data_cards_brand_grid", "editorial_split"):
            html = _render(_base_slide(pattern_type=pattern_type, canvas_elements=[
                {"x": 10, "y": 10, "size": 20, "type": "text", "content": f"marker-{pattern_type}"},
            ]))
            assert f"marker-{pattern_type}" in html

    # -------------------------------------------------------------------
    # Text width/align — painter.py's PPTX path always sizes the text box
    # from w/h and applies center alignment via `align`; this macro
    # previously ignored both (docs/ai/contracts/artistic-generation-v2-adr.md).
    # -------------------------------------------------------------------

    def test_text_element_with_w_gets_a_width_style(self):
        html = _render(_base_slide(canvas_elements=[
            {"x": 5, "y": 8, "w": 90, "h": 12, "type": "text", "content": "Sized"},
        ]))
        assert "width: 90.0%" in html or "width: 90%" in html

    def test_text_element_without_w_has_no_width_style(self):
        # v1's existing premium canvas_elements can omit w entirely and rely on
        # shrink-to-fit sizing — must not regress to width:0%.
        html = _render(_base_slide(canvas_elements=[
            {"x": 5, "y": 8, "size": 20, "type": "text", "content": "Unsized"},
        ]))
        assert "width: 0%" not in html

    def test_text_align_center_produces_center_text_align(self):
        html = _render(_base_slide(canvas_elements=[
            {"x": 5, "y": 8, "w": 90, "h": 12, "type": "text", "content": "Centered", "align": "center"},
        ]))
        assert "text-align: center" in html

    def test_text_without_align_defaults_to_left(self):
        html = _render(_base_slide(canvas_elements=[
            {"x": 5, "y": 8, "w": 90, "h": 12, "type": "text", "content": "Left aligned"},
        ]))
        assert "text-align: left" in html
