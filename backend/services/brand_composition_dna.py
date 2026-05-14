"""
BRAND COMPOSITION DNA v3.0 — GRAMMAR TYPES ENGINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Reemplaza el sistema de layout_slugs planos por un sistema de
Grammar Types con geometrías diferenciadas por tipo narrativo.

CAMBIOS v3.0:
  - GRAMMAR_GEOMETRIES: 10 tipos con coordenadas distintas
  - get_layout_geometry(): bifurca por grammar_type, no por slug genérico
  - build_decorator_elements(): decoradores específicos por tipo
  - Canvas-aware: escala todas las geometrías al canvas real de la marca
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict
import json
import os

# ══════════════════════════════════════════════════════════════
# 1. SCHEMA: BrandCompositionPolicy
# ══════════════════════════════════════════════════════════════

@dataclass
class SlideCanvasSpec:
    width_inches: float = 13.33
    height_inches: float = 7.5
    aspect_ratio: str = "16:9"

    @property
    def is_ultra_wide(self) -> bool:
        return self.width_inches > 18.0


@dataclass
class ImageCompositionRule:
    dominant_role: str = "supporting"
    max_background_ratio: float = 0.25
    supporting_geometry: dict = field(default_factory=lambda: {
        "left": 65, "top": 20, "width": 30, "height": 60
    })
    accent_geometry: dict = field(default_factory=lambda: {
        "left": 75, "top": 15, "width": 18, "height": 28
    })
    corner_style: str = "sharp"
    corner_radius_pt: int = 0


@dataclass
class TypographyCompositionRule:
    title_size_base: int = 36
    title_size_impact: int = 84
    body_size: int = 18
    metric_size: int = 48
    title_zone: dict = field(default_factory=lambda: {
        "left": 6, "top": 8, "width": 88, "height": 20
    })
    body_zone: dict = field(default_factory=lambda: {
        "left": 6, "top": 35, "width": 55, "height": 55
    })
    bullet_symbol: str = "•"


@dataclass
class BrandCompositionPolicy:
    brand_id: int = 0
    brand_name: str = ""
    canvas: SlideCanvasSpec = field(default_factory=SlideCanvasSpec)
    image_rules: ImageCompositionRule = field(default_factory=ImageCompositionRule)
    typography: TypographyCompositionRule = field(default_factory=TypographyCompositionRule)
    image_layout_archetypes: dict = field(default_factory=dict)
    persistent_decorators: list = field(default_factory=list)
    available_layouts: list = field(default_factory=lambda: [
        "strategic_split", "executive_quote", "impact_number",
        "section_break", "case_study", "two_column",
        "cover_hero", "data_grid", "closing_cta", "marketing_hero"
    ])
    visual_density: str = "dense"
    uses_dark_overlay: bool = True
    overlay_opacity: float = 0.5

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BrandCompositionPolicy":
        policy = cls()
        policy.brand_id = data.get("brand_id", 0)
        policy.brand_name = data.get("brand_name", "")
        policy.canvas = SlideCanvasSpec(**data.get("canvas", {}))
        policy.image_rules = ImageCompositionRule(**data.get("image_rules", {}))
        policy.typography = TypographyCompositionRule(**data.get("typography", {}))
        policy.persistent_decorators = data.get("persistent_decorators", [])
        policy.available_layouts = data.get("available_layouts", cls().available_layouts)
        policy.visual_density = data.get("visual_density", "dense")
        policy.uses_dark_overlay = data.get("uses_dark_overlay", True)
        policy.image_layout_archetypes = data.get("image_layout_archetypes", {})
        policy.overlay_opacity = data.get("overlay_opacity", 0.5)
        return policy


# ══════════════════════════════════════════════════════════════
# 2. PARSER
# ══════════════════════════════════════════════════════════════

def parse_essence_to_policy(
    brand_id: int,
    brand_name: str,
    artistic_essence: dict,
    visual_dna: dict,
    source_pptx_path: str = None,
    force_width: float = None,
    force_height: float = None
) -> BrandCompositionPolicy:

    policy = BrandCompositionPolicy(brand_id=brand_id, brand_name=brand_name)
    w_in = force_width or 13.33
    h_in = force_height or 7.5
    policy.canvas = SlideCanvasSpec(width_inches=round(w_in, 2), height_inches=round(h_in, 2))

    composition = artistic_essence.get("composition_rules") or {}
    density = composition.get("visual_density", "balanced")
    img_role = "accent" if density == "dense" else "supporting"

    policy.image_rules = ImageCompositionRule(
        dominant_role=img_role,
        max_background_ratio=composition.get("max_img_ratio", 0.25),
        corner_style=artistic_essence.get("design_gestures", {}).get("corner_style", "sharp")
    )

    scale_factor = w_in / 13.33
    policy.typography = TypographyCompositionRule(
        title_size_base=int(42 * scale_factor),
        title_size_impact=int(92 * scale_factor),
        body_size=int(20 * scale_factor)
    )

    archetypes = artistic_essence.get("structural_archetypes") or {}
    persistent_blocks = archetypes.get("persistent_blocks", [])
    primary_color = visual_dna.get("primary_color", "#333333")

    decorators = []
    if not persistent_blocks:
        decorators.append({
            "decorator_type": "accent_line",
            "geometry": {"left": 0, "top": 0, "width": 100, "height": 1.5},
            "color": primary_color,
            "opacity": 1.0
        })
    policy.persistent_decorators = decorators
    return policy


# ══════════════════════════════════════════════════════════════
# 3. GRAMMAR GEOMETRIES — el corazón del cambio v3.0
# ══════════════════════════════════════════════════════════════

GRAMMAR_GEOMETRIES = {

    "strategic_split": {
        "title":   {"left": 7.0,  "top": 7.0,  "width": 44.0, "height": 22.0},
        "content": {"left": 7.0,  "top": 32.0, "width": 44.0, "height": 58.0},
        "image":   {"left": 55.0, "top": 8.0,  "width": 38.0, "height": 84.0, "role": "supporting"},
        "accent":  {"left": 41.0, "top": 8.0,  "width": 8.0,  "height": 8.0},
        "table":   {"left": 7.0,  "top": 55.0, "width": 44.0, "height": 35.0},
    },

    "executive_quote": {
        "title":      {"left": 5.0,  "top": 7.0,  "width": 46.0, "height": 18.0},
        "content":    {"left": 5.0,  "top": 35.0, "width": 44.0, "height": 35.0},
        "quote_mark": {"left": 5.0,  "top": 28.0, "width": 8.0,  "height": 8.0},
        "image":      {"left": 50.0, "top": 0.0,  "width": 50.0, "height": 100.0, "role": "person_bleed"},
        "badge":      {"left": 52.0, "top": 58.0, "width": 20.0, "height": 20.0, "role": "attribution_circle"},
        "accent":     {"left": 5.0,  "top": 82.0, "width": 10.0, "height": 5.0},
        "table":      None,
    },

    "impact_number": {
        "title":   {"left": 10.0, "top": 25.0, "width": 80.0, "height": 20.0},
        "content": {"left": 10.0, "top": 48.0, "width": 80.0, "height": 40.0},
        "metric":  {"left": 10.0, "top": 10.0, "width": 80.0, "height": 10.0},
        "image":   None,
        "accent":  {"left": 88, "top": 5, "width": 8, "height": 8},
        "table":   None,
        "background_shape": {"left": 0.0, "top": 0.0, "width": 100.0, "height": 100.0,
                             "role": "brand_color_bg", "opacity": 1.0},
    },

    "section_break": {
        "title":   {"left": 8.0,  "top": 30.0, "width": 84.0, "height": 40.0},
        "content": {"left": 20.0, "top": 72.0, "width": 60.0, "height": 12.0},
        "image":   None,
        "accent":  {"left": 44.0, "top": 20.0, "width": 12.0, "height": 2.0},
        "table":   None,
        "background_shape": {"left": 0.0, "top": 0.0, "width": 100.0, "height": 100.0,
                             "role": "brand_color_bg", "opacity": 1.0},
    },

    "case_study": {
        "title":   {"left": 5.0,  "top": 7.0,  "width": 55.0, "height": 18.0},
        "content": {"left": 5.0,  "top": 28.0, "width": 45.0, "height": 38.0},
        "metric":  {"left": 5.0,  "top": 68.0, "width": 45.0, "height": 24.0},
        "image":   {"left": 53.0, "top": 12.0, "width": 44.0, "height": 72.0, "role": "supporting"},
        "accent":  {"left": 5.0,  "top": 20.0, "width": 20.0, "height": 5.0},
        "table":   {"left": 5.0,  "top": 68.0, "width": 45.0, "height": 24.0},
    },

    "two_column": {
        "title":         {"left": 7.0,  "top": 7.0,  "width": 86.0, "height": 16.0},
        "content_left":  {"left": 7.0,  "top": 28.0, "width": 41.0, "height": 62.0},
        "content_right": {"left": 52.0, "top": 28.0, "width": 41.0, "height": 62.0},
        "content":       {"left": 7.0,  "top": 28.0, "width": 41.0, "height": 62.0},
        "image":         None,
        "accent":        {"left": 48.5, "top": 25.0, "width": 3.0,  "height": 65.0},
        "table":         {"left": 7.0,  "top": 28.0, "width": 86.0, "height": 62.0},
        "background_shape": {"left": 49.0, "top": 25.0, "width": 0.3, "height": 65.0,
                            "role": "column_divider", "opacity": 0.3},
    },

    "cover_hero": {
        "title":   {"left": 7.0,  "top": 35.0, "width": 60.0, "height": 30.0},
        "content": {"left": 7.0,  "top": 68.0, "width": 55.0, "height": 18.0},
        "image":   {"left": 0.0,  "top": 0.0,  "width": 100.0, "height": 100.0, "role": "background"},
        "accent":  {"left": 7.0,  "top": 30.0, "width": 15.0, "height": 1.5},
        "table":   None,
    },

    "data_grid_cards": {
        "title":   {"left": 7.0,  "top": 7.0,  "width": 86.0, "height": 16.0},
        "metrics": {"left": 7.0,  "top": 25.0, "width": 86.0, "height": 65.0}, # Contenedor de cards
        "image":   None,
        "accent":  {"left": 7.0,  "top": 24.0, "width": 10.0, "height": 0.5},
        "table":   None,
    },
}

SLUG_ALIASES = {
    "split-right":          "strategic_split",
    "full-bleed":           "cover_hero",
    "two-column":           "two_column",
    "quote-hero":           "executive_quote",
    "data-grid":            "data_grid",
    "data-cards":           "data_grid_cards",
    "marketing-hero":       "marketing_hero",
    "asymmetric-overlay":   "asymmetric_overlay",
    "editorial-magazine":   "asymmetric_overlay",
    "dark-hero":            "cover_hero",
    "section-break":        "section_break",
    "closing-cta":          "closing_cta",
    "case-study":           "case_study",
    "impact-number":        "impact_number",
}


# ══════════════════════════════════════════════════════════════
# 4. GEOMETRY ENGINE v3.0
# ══════════════════════════════════════════════════════════════

def get_layout_geometry(
    layout_slug: str,
    slide_width: float,
    slide_height: float,
    title_lines: int = 1
) -> dict:
    grammar_type = SLUG_ALIASES.get(layout_slug, layout_slug)
    base_geo = GRAMMAR_GEOMETRIES.get(grammar_type)

    if not base_geo:
        base_geo = GRAMMAR_GEOMETRIES["strategic_split"]

    import copy
    geo = copy.deepcopy(base_geo)

    if title_lines > 1 and geo.get("title"):
        extra_h = min((title_lines - 1) * 7.0, 20.0)
        geo["title"]["height"] = min(
            geo["title"]["height"] + extra_h,
            35.0
        )
        if geo.get("content"):
            new_top = geo["title"]["top"] + geo["title"]["height"] + 3.0
            content_bottom = geo["content"]["top"] + geo["content"]["height"]
            geo["content"]["top"] = new_top
            geo["content"]["height"] = max(content_bottom - new_top, 20.0)

    return geo


# ══════════════════════════════════════════════════════════════
# 5. DECORATOR BUILDER
# ══════════════════════════════════════════════════════════════

def build_decorator_elements(
    grammar_type: str,
    primary_color: str,
    secondary_color: str,
    is_dark_bg: bool = False
) -> list:
    grammar_type = SLUG_ALIASES.get(grammar_type, grammar_type)
    decorators = []

    if grammar_type == "executive_quote":
        decorators.append({
            "type": "shape", "role": "quote_mark_bg",
            "geometry": {"left": 4.5, "top": 27.5, "width": 9.0, "height": 9.0},
            "style": {"color": secondary_color, "opacity": 0.15,
                      "shape_type": "ellipse"}
        })
        decorators.append({
            "type": "shape", "role": "attribution_badge",
            "geometry": {"left": 52.5, "top": 58.5, "width": 19.0, "height": 19.0},
            "style": {"color": secondary_color, "opacity": 1.0,
                      "shape_type": "ellipse"}
        })
        decorators.append({
            "type": "shape", "role": "overlay",
            "geometry": {"left": 50.0, "top": 0.0, "width": 50.0, "height": 100.0},
            "style": {"color": "#000000", "opacity": 0.15}
        })

    elif grammar_type in ("impact_number", "section_break", "closing_cta"):
        decorators.append({
            "type": "shape", "role": "brand_color_bg",
            "geometry": {"left": 0.0, "top": 0.0, "width": 100.0, "height": 100.0},
            "style": {"color": primary_color, "opacity": 1.0}
        })
        decorators.append({
            "type": "shape", "role": "accent_line",
            "geometry": {"left": 8.0, "top": 15.0, "width": 20.0, "height": 0.6},
            "style": {"color": secondary_color, "opacity": 0.8}
        })

    elif grammar_type == "cover_hero":
        decorators.append({
            "type": "shape", "role": "overlay",
            "geometry": {"left": 0.0, "top": 0.0, "width": 65.0, "height": 100.0},
            "style": {"color": "#000000", "opacity": 0.55}
        })
        decorators.append({
            "type": "shape", "role": "title_underline",
            "geometry": {"left": 7.0, "top": 66.0, "width": 18.0, "height": 0.6},
            "style": {"color": secondary_color, "opacity": 1.0}
        })

    elif grammar_type == "two_column":
        decorators.append({
            "type": "shape", "role": "column_divider",
            "geometry": {"left": 49.3, "top": 24.0, "width": 0.4, "height": 67.0},
            "style": {"color": primary_color, "opacity": 0.2}
        })

    elif grammar_type == "case_study":
        decorators.append({
            "type": "shape", "role": "accent_line",
            "geometry": {"left": 5.0, "top": 26.0, "width": 20.0, "height": 0.5},
            "style": {"color": secondary_color, "opacity": 1.0}
        })
        decorators.append({
            "type": "shape", "role": "metrics_panel",
            "geometry": {"left": 4.5, "top": 67.0, "width": 46.0, "height": 26.0},
            "style": {"color": primary_color, "opacity": 0.06}
        })

    elif grammar_type == "data_grid":
        decorators.append({
            "type": "shape", "role": "section_rule",
            "geometry": {"left": 7.0, "top": 24.0, "width": 86.0, "height": 0.4},
            "style": {"color": primary_color, "opacity": 0.3}
        })

    elif grammar_type == "asymmetric_overlay":
        decorators.append({
            "type": "shape", "role": "frosted_panel",
            "geometry": {"left": 3.0, "top": 8.0, "width": 50.0, "height": 84.0},
            "style": {"color": "#FFFFFF", "opacity": 0.88}
        })

    if grammar_type not in ("impact_number", "section_break", "closing_cta", "cover_hero"):
        decorators.append({
            "type": "shape", "role": "top_brand_bar",
            "geometry": {"left": 0.0, "top": 0.0, "width": 100.0, "height": 1.2},
            "style": {"color": primary_color, "opacity": 1.0}
        })
        decorators.append({
            "type": "shape", "role": "brand_dot",
            "geometry": {"left": 1.2, "top": 94.0, "width": 2.2, "height": 4.0},
            "style": {"color": secondary_color, "opacity": 1.0}
        })

    return decorators


# ══════════════════════════════════════════════════════════════
# 6. GRAMMAR TYPE SELECTOR
# ══════════════════════════════════════════════════════════════

def infer_grammar_type(
    slide_number: int,
    total_slides: int,
    title: str,
    bullets: list,
    metric: str = None,
    layout_intent: str = "",
    recent_types: list = None
) -> str:
    if recent_types is None:
        recent_types = []

    title_lower = title.lower()
    intent_lower = layout_intent.lower()

    if slide_number == 1:
        return "cover_hero"

    if slide_number >= total_slides - 1 and "conclusion" in title_lower:
        return "closing_cta"

    if not bullets and len(title) < 40 and "section" in intent_lower:
        return "section_break"

    if any(w in title_lower for w in ["testimonial", "ceo", "quote", "perspective", "said"]):
        return "executive_quote"

    if any(w in title_lower for w in ["case study", "case_study", "retailer", "coles", "loblaw", "conad"]):
        return "case_study"

    if metric or any(w in title_lower for w in ["kpi", "metric", "roi", "revenue", "growth", "%", "at a glance"]):
        # v24.0: Prefer structured cards for multiple metrics
        if bullets and len(bullets) >= 2 and any(any(c.isdigit() for c in b) for b in bullets):
            return "data_grid_cards"
        if recent_types.count("impact_number") < 2:
            return "impact_number"

    if any(w in title_lower for w in ["comparison", "vs", "before", "after", "versus"]):
        return "two_column"

    if "data" in intent_lower or "grid" in intent_lower:
        return "data_grid"

    if recent_types[-3:].count("strategic_split") >= 3:
        return "two_column"

    return "strategic_split"


# ══════════════════════════════════════════════════════════════
# 7. BUILD SLIDE ELEMENTS (Legacy Support)
# ══════════════════════════════════════════════════════════════

def build_slide_elements(
    slide: dict,
    slide_type: str,
    slide_index: int,
    total_slides: int,
    policy: BrandCompositionPolicy,
    visual_dna: dict,
    full_bleed_budget: dict,
    font_scale_override: float = 1.0
) -> tuple:
    return [], "default"
