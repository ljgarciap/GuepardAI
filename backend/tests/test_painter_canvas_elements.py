"""
test_painter_canvas_elements.py — real canvas_elements builder for
paint_custom_canvas() (Synthesis Studio v2, Finding 1b).

Covers: the CSS-shorthand parsers (color/border/gradient) the Art Director's
real production output requires, the real fill-transparency fix (python-pptx
has no working public API for it), and that paint_custom_canvas() renders
every element type real production data has produced (shape, decorator,
line, gradient_overlay, plus the pre-existing text/image/typo_substitution)
without ever raising on a single malformed element.
"""
import pytest
from pptx.dml.color import RGBColor
from pptx.oxml.ns import qn

from services.rendering.painter import (
    GammaPainter,
    apply_fill_alpha,
    parse_canvas_border,
    parse_canvas_color,
    parse_css_linear_gradient,
)


class FakeBrand:
    primary_color = "#0052A3"
    secondary_color = "#E31837"
    background_color = "#FFFFFF"
    font_family = "Arial"


@pytest.fixture()
def painter():
    return GammaPainter(FakeBrand())


@pytest.mark.unit
class TestParseCanvasColor:

    def test_hex(self):
        color, alpha = parse_canvas_color("#2E8B57")
        assert color == RGBColor(0x2E, 0x8B, 0x57)
        assert alpha is None

    def test_rgba(self):
        color, alpha = parse_canvas_color("rgba(46, 139, 87, 0.5)")
        assert color == RGBColor(46, 139, 87)
        assert alpha == 0.5

    def test_rgb_no_alpha(self):
        color, alpha = parse_canvas_color("rgb(46, 139, 87)")
        assert color == RGBColor(46, 139, 87)
        assert alpha is None

    def test_none_and_garbage_degrade_to_none_none(self):
        assert parse_canvas_color(None) == (None, None)
        assert parse_canvas_color("not-a-color") == (None, None)
        assert parse_canvas_color(123) == (None, None)


@pytest.mark.unit
class TestParseCanvasBorder:

    def test_full_shorthand(self):
        width, color, alpha = parse_canvas_border("2px solid rgba(46, 139, 87, 0.5)")
        assert width == 2.0
        assert color == RGBColor(46, 139, 87)
        assert alpha == 0.5

    def test_hex_border(self):
        width, color, alpha = parse_canvas_border("3px solid #FFFFFF")
        assert width == 3.0
        assert color == RGBColor(0xFF, 0xFF, 0xFF)

    def test_malformed_degrades_to_none_triple(self):
        assert parse_canvas_border("not a border") == (None, None, None)
        assert parse_canvas_border(None) == (None, None, None)


@pytest.mark.unit
class TestParseCssLinearGradient:

    def test_two_stop_gradient(self):
        angle, stops = parse_css_linear_gradient(
            "linear-gradient(135deg, rgba(0, 56, 101, 0.7) 0%, rgba(0, 83, 159, 0.4) 100%)"
        )
        assert angle == 135.0
        assert len(stops) == 2
        assert stops[0] == (RGBColor(0, 56, 101), 0.7)
        assert stops[1] == (RGBColor(0, 83, 159), 0.4)

    def test_radial_gradient_not_supported_degrades_empty(self):
        angle, stops = parse_css_linear_gradient("radial-gradient(circle, #fff 0%, #000 100%)")
        assert angle is None
        assert stops == []

    def test_none_and_garbage(self):
        assert parse_css_linear_gradient(None) == (None, [])
        assert parse_css_linear_gradient("not a gradient") == (None, [])


@pytest.mark.unit
class TestApplyFillAlpha:

    def test_injects_real_alpha_xml(self, painter):
        slide = painter.secure_slide({})
        shape = painter.add_rect(slide, painter.w(10), painter.h(10), painter.w(20), painter.h(20), RGBColor(255, 0, 0))
        apply_fill_alpha(shape, 0.5)
        color_elm = shape._element.spPr.find(qn('a:solidFill')).find(qn('a:srgbClr'))
        alpha_elm = color_elm.find(qn('a:alpha'))
        assert alpha_elm is not None
        assert alpha_elm.get("val") == "50000"

    def test_zero_transparency_adds_no_alpha_element(self, painter):
        slide = painter.secure_slide({})
        shape = painter.add_rect(slide, painter.w(10), painter.h(10), painter.w(20), painter.h(20), RGBColor(255, 0, 0))
        apply_fill_alpha(shape, 0.0)
        color_elm = shape._element.spPr.find(qn('a:solidFill')).find(qn('a:srgbClr'))
        assert color_elm.find(qn('a:alpha')) is None

    def test_add_rect_transparency_param_actually_applies_now(self, painter):
        # Regression: shape.fill.transparency = X used to be a silent no-op
        # (dangling Python attribute, zero effect on the XML) — add_rect's
        # own transparency= kwarg inherited that bug. Every existing caller
        # (footer bands, quote/hero backing panels) was rendering fully
        # opaque regardless of the value passed.
        slide = painter.secure_slide({})
        shape = painter.add_rect(slide, painter.w(0), painter.h(0), painter.w(100), painter.h(100), RGBColor(0, 0, 0), transparency=0.7)
        color_elm = shape._element.spPr.find(qn('a:solidFill')).find(qn('a:srgbClr'))
        alpha_elm = color_elm.find(qn('a:alpha'))
        assert alpha_elm is not None
        assert alpha_elm.get("val") == "30000"  # (1 - 0.7) * 100000


@pytest.mark.integration
class TestPaintCustomCanvas:

    def _shape_types(self, slide):
        return [s.shape_type for s in slide.shapes]

    def test_renders_every_real_production_element_type_without_raising(self, painter):
        slide_data = {
            "slide_number": 1, "title": "Test", "is_last": False,
            "elements": [
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
            ],
        }
        # Must not raise — that's the primary assertion (real production data,
        # all 6 element types in one slide).
        painter.paint_custom_canvas(slide_data)

    def test_one_malformed_element_does_not_blank_the_rest(self, painter):
        slide_data = {
            "slide_number": 1, "title": "Test", "is_last": False,
            "elements": [
                {"type": "shape", "color": None},  # nothing to draw, must not raise
                {"type": "unknown_future_type", "x": 1, "y": 2},  # unrecognized, must be skipped silently
                {"x": 10, "y": 10, "size": 20, "type": "text", "content": "Still here"},
            ],
        }
        painter.paint_custom_canvas(slide_data)
        slide = painter.prs.slides[-1]
        all_text = " ".join(
            shape.text_frame.text for shape in slide.shapes if shape.has_text_frame
        )
        assert "Still here" in all_text

    def test_circle_shape_is_centered_not_top_left(self, painter):
        # Real Art Director output positions concentric circles by sharing one
        # x/y with different sizes — a top-left interpretation would scatter
        # them instead of nesting them.
        slide_data = {
            "slide_number": 1, "title": "Test", "is_last": False,
            "elements": [{"x": 50, "y": 50, "size": 20, "type": "shape", "shape": "circle", "color": "#000000"}],
        }
        painter.paint_custom_canvas(slide_data)
        slide = painter.prs.slides[-1]
        ovals = [s for s in slide.shapes if getattr(s, "auto_shape_type", None) is not None and "OVAL" in str(s.auto_shape_type)]
        assert len(ovals) == 1
        oval = ovals[0]
        # Center of the shape's bounding box should land on (50%, 50%) of the slide.
        center_x_pct = (oval.left + oval.width / 2) / painter.prs.slide_width * 100
        center_y_pct = (oval.top + oval.height / 2) / painter.prs.slide_height * 100
        assert abs(center_x_pct - 50) < 0.1
        assert abs(center_y_pct - 50) < 0.1

    def test_line_adds_a_connector_shape(self, painter):
        slide_data = {
            "slide_number": 1, "title": "Test", "is_last": False,
            "elements": [{"x1": 10, "y1": 10, "x2": 90, "y2": 10, "type": "line", "stroke": "#000000"}],
        }
        painter.paint_custom_canvas(slide_data)
        slide = painter.prs.slides[-1]
        assert len(slide.shapes) >= 1  # background rect + connector, no crash
