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
    persistent_decorators: list = field(default_factory=list)
    available_layouts: list = field(default_factory=lambda: [
        "split-right", "text-only", "full-bleed", "two-column", "quote-hero"
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
        policy.overlay_opacity = data.get("overlay_opacity", 0.5)
        return policy

# ══════════════════════════════════════════════════════════════
# 2. PARSER: Convertir esencia en política determinista
# ══════════════════════════════════════════════════════════════

def parse_essence_to_policy(brand_id: int, brand_name: str, artistic_essence: dict, visual_dna: dict, source_pptx_path: str = None) -> BrandCompositionPolicy:
    """
    TRULY AGNOSTIC PARSER.
    Detecta dimensiones y reglas a partir del manual de marca real (source_pptx)
    y de la esencia extraída por la IA. Cero hardcoding.
    """
    policy = BrandCompositionPolicy(brand_id=brand_id, brand_name=brand_name)
    
    # 1. Detección Dinámica de Canvas
    # Leemos las dimensiones reales del archivo fuente (manual de marca)
    w_in, h_in = 13.33, 7.5
    if source_pptx_path and os.path.exists(source_pptx_path):
        try:
            from pptx import Presentation
            prs = Presentation(source_pptx_path)
            w_in, h_in = prs.slide_width.inches, prs.slide_height.inches
        except: pass
    
    policy.canvas = SlideCanvasSpec(
        width_inches=round(w_in, 2), 
        height_inches=round(h_in, 2), 
        aspect_ratio="custom" if w_in > 14 else "16:9"
    )

    # 2. Factor de Escala Universal
    # Todas las fuentes y grosores se escalan proporcionalmente al ancho del lienzo
    scale_factor = w_in / 13.33

    # 3. Reglas de Imagen basadas en Densidad (Extraída por IA)
    composition = artistic_essence.get("composition_rules", {})
    density = composition.get("visual_density", "balanced")
    
    # Si la esencia dice que la marca es 'dense' (como Tesco), las imágenes son acentos.
    # Si es 'minimal' (como Apple), pueden ser más grandes.
    img_role = "accent" if density == "dense" else "supporting"
    
    policy.image_rules = ImageCompositionRule(
        dominant_role=img_role,
        max_background_ratio=composition.get("max_img_ratio", 0.25),
        corner_style=artistic_essence.get("design_gestures", {}).get("corner_style", "sharp")
    )

    # 5. Zonificación Estructural (Look Agencia v16.2)
    # Matamos el look de Word inyectando zonificación de color y profundidad.
    design_gestures = artistic_essence.get("design_gestures", {})
    primary_color = visual_dna.get("primary_color", "#333333")
    secondary_color = visual_dna.get("secondary_color", "#CCCCCC")

    decorators = []
    
    # Gesto A: Sidebar de Marca (Crea estructura inmediata)
    decorators.append({
        "decorator_type": "sidebar_zone", 
        "geometry": {"left": 0, "top": 0, "width": 4, "height": 100}, 
        "color": primary_color, "opacity": 1.0
    })
    
    # Gesto B: Content Panel (Para que los bullets no floten)
    decorators.append({
        "decorator_type": "content_panel", 
        "geometry": {"left": 8, "top": 30, "width": 55, "height": 60}, 
        "color": "#F9F9F9", "opacity": 0.5
    })
    
    # Gesto C: Brand Accent (Barra de título dinámica)
    decorators.append({
        "decorator_type": "brand_bar", 
        "geometry": {"left": 8, "top": 8, "width": 10, "height": 0.4}, 
        "color": primary_color, "opacity": 1.0
    })
    
    # Gesto D: Secondary Decorator (Puntos o líneas de acento)
    decorators.append({
        "decorator_type": "corner_accent", 
        "geometry": {"left": 96, "top": 0, "width": 4, "height": 12}, 
        "color": secondary_color, "opacity": 0.8
    })

    policy.persistent_decorators = decorators
    policy.uses_dark_overlay = True
    policy.overlay_opacity = 0.4
    
    return policy

def build_slide_elements(slide: dict, slide_type: str, slide_index: int, total_slides: int, policy: BrandCompositionPolicy, visual_dna: dict, full_bleed_budget: dict) -> tuple:
    elements = []
    primary = visual_dna.get("primary_color", "#0052A3")
    secondary = visual_dna.get("secondary_color", "#EE1C2E")
    bg_color = visual_dna.get("background_color", "#FFFFFF")
    font_main = visual_dna.get("primary_font", "Arial")
    
    is_impact = (slide_type == "title" or slide_index == 0)
    use_full_bleed = is_impact and full_bleed_budget["used"] < full_bleed_budget["max"]
    if use_full_bleed: full_bleed_budget["used"] += 1

    layout = "full-bleed" if use_full_bleed else "split-right"
    
    # 1. CAPA BASE: Fondo
    elements.append({"type": "background_color", "color": bg_color if not use_full_bleed else "#000000", "geometry": {"left": 0, "top": 0, "width": 100, "height": 100}})

    # 2. CAPA DE IMAGEN
    if use_full_bleed:
        elements.append({"type": "image", "role": "background", "source": slide.get("slide_number"), "geometry": {"left": 0, "top": 0, "width": 100, "height": 100}})
        elements.append({"type": "shape", "role": "overlay", "geometry": {"left": 0, "top": 0, "width": 100, "height": 100}, "style": {"color": "#000000", "opacity": policy.overlay_opacity}})
    elif layout == "split-right":
        geom = policy.image_rules.accent_geometry if policy.image_rules.dominant_role == "accent" else policy.image_rules.supporting_geometry
        elements.append({"type": "image", "role": "accent", "source": slide.get("slide_number"), "geometry": geom, "style": {"corner_style": policy.image_rules.corner_style}})

    # 3. CAPA ESTRUCTURAL: Zonas y Decoradores
    for dec in policy.persistent_decorators:
        if use_full_bleed and dec["decorator_type"] in ("sidebar_zone", "content_panel"): continue
        elements.append({"type": "shape", "role": dec["decorator_type"], "geometry": dec["geometry"], "style": {"color": dec["color"], "opacity": dec["opacity"]}})

    # 4. CAPA DE MICRO-DATOS
    elements.append({"type": "text", "role": "page_num", "content": f"{slide_index + 1}", "geometry": {"left": 92, "top": 93, "width": 4, "height": 3}, "style": {"font": font_main, "size": 10, "color": primary, "opacity": 0.5}})

    # 5. CAPA DE TEXTO (Jerarquía Premium)
    typo = policy.typography
    t_size = typo.title_size_impact if use_full_bleed else typo.title_size_base
    t_color = "#FFFFFF" if use_full_bleed else primary
    
    elements.append({
        "type": "text", "role": "title", "content": slide.get("title", ""), 
        "geometry": {"left": 8, "top": 12, "width": 80, "height": 15}, 
        "style": {"font": font_main, "size": t_size, "color": t_color, "bold": True}
    })

    if slide.get("bullets"):
        b_color = "#EEEEEE" if use_full_bleed else "#333333"
        elements.append({
            "type": "text", "role": "bullets", "content": "\n".join([f"• {b}" for b in slide["bullets"]]), 
            "geometry": {"left": 9, "top": 35, "width": 50, "height": 55}, 
            "style": {"font": font_main, "size": typo.body_size, "color": b_color}
        })
        
    # Gesto extra: Métrica o subtítulo en color secundario
    if slide.get("metric"):
        elements.append({
            "type": "text", "role": "metric", "content": slide["metric"], 
            "geometry": {"left": 9, "top": 85, "width": 50, "height": 5}, 
            "style": {"font": font_main, "size": typo.body_size - 2, "color": secondary, "bold": True}
        })

    return elements, layout
