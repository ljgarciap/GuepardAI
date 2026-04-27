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
    image_layout_archetypes: Optional[dict] = None
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

def parse_essence_to_policy(brand_id: int, brand_name: str, artistic_essence: dict, visual_dna: dict, source_pptx_path: str = None, force_width: float = None, force_height: float = None) -> BrandCompositionPolicy:
    """
    TRULY AGNOSTIC PARSER v16.3.
    """
    policy = BrandCompositionPolicy(brand_id=brand_id, brand_name=brand_name)
    
    # 1. Detección Dinámica de Canvas (Fix 1: Dimensiones reales de DB)
    w_in = force_width or 13.33
    h_in = force_height or 7.5
    
    policy.canvas = SlideCanvasSpec(
        width_inches=round(w_in, 2), 
        height_inches=round(h_in, 2), 
        aspect_ratio="custom" if w_in > 14 else "16:9"
    )

    # 2. Factor de Escala Universal
    scale_factor = w_in / 13.33

    # 3. Reglas de Imagen (Densidad basada en RAG)
    composition = artistic_essence.get("composition_rules", {})
    density = composition.get("visual_density", "balanced")
    img_role = "accent" if density == "dense" else "supporting"
    
    policy.image_rules = ImageCompositionRule(
        dominant_role=img_role,
        max_background_ratio=composition.get("max_img_ratio", 0.25),
        corner_style=artistic_essence.get("design_gestures", {}).get("corner_style", "sharp")
    )

    # 4. Tipografía Paramétrica (Fix 3: Aumento de tamaño y aire)
    policy.typography = TypographyCompositionRule(
        title_size_base=int(34 * scale_factor),
        title_size_impact=int(86 * scale_factor), 
        body_size=int(18 * scale_factor),
        metric_size=int(52 * scale_factor)
    )
    
    # 5. Zonificación Estructural Dinámica (v17.0 - High Fidelity)
    # Ya no interpretamos gestos vagos, dibujamos bloques mapeados por la IA.
    archetypes = artistic_essence.get("structural_archetypes", {})
    persistent_blocks = archetypes.get("persistent_blocks", [])
    
    primary_color = visual_dna.get("primary_color", "#333333")
    secondary_color = visual_dna.get("secondary_color", "#CCCCCC")
    bg_color = visual_dna.get("background_color", "#FFFFFF")

    decorators = []
    
    # Renderizar bloques persistentes (Sidebars, Headers, Footers mapeados)
    for block in persistent_blocks:
        role = block.get("role", "sidebar")
        geom = block.get("geometry", {})
        color_source = block.get("color_source", "primary")
        # Mapeo de color basado en rol (v17.2)
        if color_source == "primary":
            target_color = primary_color
        elif color_source == "background":
            target_color = bg_color
        else:
            target_color = secondary_color
        
        decorators.append({
            "decorator_type": f"{role}_zone", 
            "geometry": geom, 
            "color": target_color, 
            "opacity": 1.0
        })

    # 6. Reglas de Imagen e Impacto
    design_gestures = artistic_essence.get("design_gestures", {})
    policy.image_rules.corner_style = design_gestures.get("corner_style", "sharp")
    
    policy.image_layout_archetypes = artistic_essence.get("slide_archetypes", {})
    policy.persistent_decorators = decorators
    policy.uses_dark_overlay = True
    policy.overlay_opacity = artistic_essence.get("composition_rules", {}).get("overlay_opacity", 0.4)
    
    return policy

def build_slide_elements(slide: dict, slide_type: str, slide_index: int, total_slides: int, policy: BrandCompositionPolicy, visual_dna: dict, full_bleed_budget: dict, font_scale_override: float = 1.0) -> tuple:
    """
    BIFURCADOR DE LAYOUTS (v18.0).
    Soporta overrides del Director de Arte LLM.
    """
    primary = visual_dna.get("primary_color", "#0052A3")
    secondary = visual_dna.get("secondary_color", "#EE1C2E")
    bg_color = visual_dna.get("background_color", "#FFFFFF")
    font_main = visual_dna.get("primary_font", "Arial")
    typo = policy.typography
    
    # 1. Determinación de Impacto
    is_impact = (slide_type == "full-bleed" or slide_type == "title")
    
    # Imagen asignada semánticamente por el Art Director
    image_source = slide.get("assigned_image", slide.get("slide_number"))

    # 2. Selección de Layout con Escalado Dinámico
    if is_impact:
        return _build_full_bleed_layout(slide, policy, font_main, typo, font_scale_override, image_source), "full-bleed"
    
    if slide_type == "data":
        return _build_data_layout(slide, policy, primary, secondary, font_main, typo, font_scale_override, image_source), "data-grid"
    
    if slide_type == "image_hero":
        return _build_quote_layout(slide, policy, primary, secondary, font_main, typo, font_scale_override, image_source), "centered-quote"
    
    if slide_type == "conclusion":
        return _build_conclusion_layout(slide, policy, primary, bg_color, font_main, typo, font_scale_override), "brand-solid"

    # Default: Content Layout
    return _build_content_layout(slide, slide_index, policy, primary, bg_color, font_main, typo, font_scale_override, image_source), "standard-content"

# ──────────────────────────────────────────────
# ARCHETYPES (Templates Específicos)
# ──────────────────────────────────────────────

def _build_full_bleed_layout(slide, policy, font, typo, scale, source):
    elements = []
    elements.append({"type": "background_color", "color": "#000000", "geometry": {"left": 0, "top": 0, "width": 100, "height": 100}})
    elements.append({"type": "image", "role": "background", "source": source, "geometry": {"left": 0, "top": 0, "width": 100, "height": 100}})
    elements.append({"type": "shape", "role": "overlay", "geometry": {"left": 0, "top": 0, "width": 100, "height": 100}, "style": {"color": "#000000", "opacity": policy.overlay_opacity}})
    
    # Texto de impacto (Reducido si el Art Director lo pide para evitar tapar caras)
    elements.append({
        "type": "text", "role": "title", "content": slide.get("title", ""), 
        "geometry": {"left": 8, "top": 15, "width": 80, "height": 20}, 
        "style": {"font": font, "size": int(typo.title_size_impact * scale), "color": "#FFFFFF", "bold": True, "align": "center"}
    })
    return elements

def _build_content_layout(slide, index, policy, primary, bg, font, typo, scale, source):
    elements = []
    elements.append({"type": "background_color", "color": bg, "geometry": {"left": 0, "top": 0, "width": 100, "height": 100}})
    
    # 1. Re-inyectar decoradores estructurales (Zonas de marca)
    for dec in policy.persistent_decorators:
        elements.append({"type": "shape", "role": dec["decorator_type"], "geometry": dec["geometry"], "style": {"color": dec["color"], "opacity": dec["opacity"]}})
    
    # 2. Selección de Layout de Imagen según Arquetipo
    arch = policy.image_layout_archetypes.get("content", {})
    layout_type = arch.get("layout", "split-right")
    
    img_geom = {"left": 55, "top": 20, "width": 40, "height": 65} # Default Split-Right
    if layout_type == "accent-box":
        img_geom = {"left": 65, "top": 25, "width": 25, "height": 40}
    elif layout_type == "sidebar-left":
        # Si la marca tiene sidebar a la izquierda, la imagen suele ir a la derecha
        img_geom = {"left": 60, "top": 25, "width": 30, "height": 50}

    # 3. Inyectar Imagen con Estilo (Sombra, Marco, Esquinas)
    img_style = {
        "corner_style": policy.image_rules.corner_style,
        "shadow": True, # Forzado por Tesco manual
        "has_frame": True
    }
    
    elements.append({
        "type": "image", "role": "supporting", "source": source, 
        "geometry": img_geom, 
        "style": img_style
    })
    
    # 4. Textos con Aire
    elements.append({"type": "text", "role": "page_num", "content": f"{index + 1}", "geometry": {"left": 92, "top": 93, "width": 4, "height": 3}, "style": {"font": font, "size": int(10 * scale), "color": primary, "opacity": 0.5}})

    elements.append({
        "type": "text", "role": "title", "content": slide.get("title", ""), 
        "geometry": {"left": 8, "top": 12, "width": 50, "height": 15}, 
        "style": {"font": font, "size": int(typo.title_size_base * scale), "color": primary, "bold": True}
    })

    if slide.get("bullets"):
        elements.append({
            "type": "text", "role": "bullets", "content": "\n".join([f"• {b}" for b in slide["bullets"]]), 
            "geometry": {"left": 9, "top": 32, "width": 52, "height": 55}, 
            "style": {"font": font, "size": typo.body_size, "color": "#333333"}
        })
    return elements

def _build_data_layout(slide, policy, primary, secondary, font, typo, scale, source):
    elements = []
    elements.append({"type": "background_color", "color": "#FFFFFF", "geometry": {"left": 0, "top": 0, "width": 100, "height": 100}})
    for dec in policy.persistent_decorators:
        elements.append({"type": "shape", "role": dec["decorator_type"], "geometry": dec["geometry"], "style": {"color": dec["color"], "opacity": dec["opacity"]}})

    elements.append({
        "type": "text", "role": "title", "content": slide.get("title", ""), 
        "geometry": {"left": 10, "top": 15, "width": 80, "height": 10}, 
        "style": {"font": font, "size": int(typo.title_size_base * scale), "color": primary, "bold": True, "align": "center"}
    })
    
    if slide.get("metric"):
        elements.append({
            "type": "text", "role": "metric", "content": slide["metric"], 
            "geometry": {"left": 10, "top": 35, "width": 80, "height": 35}, 
            "style": {"font": font, "size": int((typo.metric_size + 10) * scale), "color": secondary, "bold": True, "align": "center"}
        })
    return elements

def _build_quote_layout(slide, policy, primary, secondary, font, typo, scale, source):
    elements = []
    elements.append({"type": "background_color", "color": "#FFFFFF", "geometry": {"left": 0, "top": 0, "width": 100, "height": 100}})
    for dec in policy.persistent_decorators:
        elements.append({"type": "shape", "role": dec["decorator_type"], "geometry": dec["geometry"], "style": {"color": dec["color"], "opacity": dec["opacity"]}})

    elements.append({
        "type": "text", "role": "bullets", "content": f"\"{slide.get('title', '')}\"", 
        "geometry": {"left": 15, "top": 20, "width": 70, "height": 45}, 
        "style": {"font": font, "size": int((typo.title_size_base + 8) * scale), "color": primary, "italic": True, "align": "center"}
    })
    
    elements.append({
        "type": "image", "role": "person", "source": source, 
        "geometry": {"left": 40, "top": 65, "width": 20, "height": 30}, 
        "style": {"corner_style": "rounded"}
    })
    return elements

def _build_conclusion_layout(slide, policy, primary, bg, font, typo, scale):
    elements = []
    # Fondo sólido de marca
    elements.append({"type": "background_color", "color": primary, "geometry": {"left": 0, "top": 0, "width": 100, "height": 100}})
    
    elements.append({
        "type": "text", "role": "title", "content": slide.get("title", ""), 
        "geometry": {"left": 10, "top": 40, "width": 80, "height": 20}, 
        "style": {"font": font, "size": typo.title_size_impact, "color": "#FFFFFF", "bold": True, "align": "center"}
    })
    return elements
