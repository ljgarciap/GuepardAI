"""
BRAND COMPOSITION DNA v2.0 — ANALYST VISION ALIGNED
Este módulo implementa la capa de composición determinista sugerida por el analista.
Evita la variabilidad del LLM en renderizado y asegura fidelidad de canvas y geometría.
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
    """Dimensiones físicas reales del slide."""
    width_inches: float = 13.33
    height_inches: float = 7.5
    aspect_ratio: str = "16:9"

    @property
    def is_ultra_wide(self) -> bool:
        return self.width_inches > 18.0

@dataclass
class ImageCompositionRule:
    """Reglas de rol y tamaño de imagen (Tesco Vision: accent/small)."""
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
    """Escalas tipográficas proporcionales al canvas real."""
    title_size_base: int = 36
    title_size_impact: int = 84     # Tesco: títulos masivos en canvas wide
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
        "split-right", "text-only", "full-bleed", "two-column", "quote-hero", "marketing-hero"
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

def parse_essence_to_policy(brand_id: int, brand_name: str, artistic_essence: dict, visual_dna: dict, source_pptx_path: str = None, force_width: float = None, force_height: float = None) -> BrandCompositionPolicy:
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
# 3. GEOMETRY ENGINE (v32.5 - Percentage Based)
# ══════════════════════════════════════════════════════════════

def get_layout_geometry(layout_slug: str, slide_width: float, slide_height: float, title_lines: int = 1) -> dict:
    """
    Calcula la geometría en PORCENTAJES (0-100).
    Compatible con los helpers sx() y sy() del renderizador.
    """
    margin_x = 7.0
    margin_y = 7.0
    usable_w = 100.0 - (2 * margin_x)
    
    # Altura del título en %
    title_h = 10.0 * title_lines
    if title_lines > 2: title_h = 8.0 * title_lines
    if title_h > 35.0: title_h = 35.0
    
    content_y = margin_y + title_h + 3.0
    remaining_h = 93.0 - content_y

    geo = {
        "title": {"top": margin_y, "left": margin_x, "width": usable_w, "height": title_h},
        "content": {"top": content_y, "left": margin_x, "width": usable_w, "height": remaining_h},
        "image": None
    }

    if layout_slug in ["marketing-hero", "split-right"]:
        geo["content"]["width"] = 45.0
        geo["title"]["width"] = 45.0
        geo["image"] = {
            "top": margin_y,
            "left": 55.0,
            "width": 38.0,
            "height": 100.0 - (2 * margin_y)
        }
    
    elif layout_slug == "two-column":
        col_w = (usable_w - 4.0) / 2
        geo["content_left"] = {"top": content_y, "left": margin_x, "width": col_w, "height": remaining_h}
        geo["content_right"] = {"top": content_y, "left": margin_x + col_w + 4.0, "width": col_w, "height": remaining_h}

    return geo

# ══════════════════════════════════════════════════════════════
# 4. ELEMENT BUILDER (Legacy/Support)
# ══════════════════════════════════════════════════════════════

def build_slide_elements(slide: dict, slide_type: str, slide_index: int, total_slides: int, policy: BrandCompositionPolicy, visual_dna: dict, full_bleed_budget: dict, font_scale_override: float = 1.0) -> tuple:
    # Mantenemos esta firma para compatibilidad, aunque el ArtDirector ahora es el que manda.
    return [], "default"
