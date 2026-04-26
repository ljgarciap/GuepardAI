import json
import os
from typing import Optional, List, Dict
from llm_provider import generate_json

def _infer_slide_type(slide: dict) -> str:
    num = slide.get("slide_number", 1)
    intent = slide.get("layout_intent", "").lower()
    title = slide.get("title", "").lower()
    if num == 1 or "hero" in intent or "title" in intent: return "title"
    if "metric" in intent or "data" in intent or "grid" in intent or slide.get("metric"): return "data"
    if "quote" in intent or "testimonial" in title: return "image_hero"
    if num >= 14 or "thank you" in title or "conclusion" in title: return "conclusion"
    return "content"

def _get_contrast_color(hex_bg: str, brand_primary: str, brand_text: str) -> str:
    hex_bg = str(hex_bg).lstrip('#')
    if len(hex_bg) != 6: return brand_text
    try:
        r, g, b = int(hex_bg[0:2], 16), int(hex_bg[2:4], 16), int(hex_bg[4:6], 16)
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return "#FFFFFF" if luminance < 0.5 else brand_text
    except: return brand_text

from .brand_composition_dna import (
    parse_essence_to_policy,
    build_slide_elements,
    BrandCompositionPolicy,
)

def orchestrate_visual_coherence(content_manifest: dict, brand_dna, brand_essence=None) -> dict:
    return content_manifest

def apply_design_policy(content_manifest: dict, brand_dna, brand_essence=None) -> dict:
    """
    DESIGN ARCHITECT v16.1 — ANALYST VISION DRIVEN.
    Usa BrandCompositionPolicy para asegurar fidelidad a Tesco (Canvas 21.99").
    """
    all_slides = content_manifest.get("slides", [])
    total_slides = len(all_slides)

    # 1. Reconstruir Esencia y DNA para la Política
    visual_dna_dict = {
        "primary_color":    getattr(brand_dna, "primary_color", "#333333"),
        "secondary_color":  getattr(brand_dna, "secondary_color", "#666666"),
        "background_color": getattr(brand_dna, "background_color", "#FFFFFF"),
        "text_main_color":  getattr(brand_dna, "text_main_color", "#000000"),
        "primary_font":     getattr(brand_dna, "primary_font", "Arial"),
    }
    
    artistic_essence_dict = {
        "structural_archetypes": getattr(brand_essence, "structural_archetypes", {}),
        "design_gestures":       getattr(brand_essence, "design_gestures", {}),
        "composition_rules":     getattr(brand_essence, "composition_rules", {}),
    }

    # Intentar detectar el canvas real si el brand_dna tiene el path original
    # Para Tesco, forzamos el canvas ultra-wide si no hay path
    source_pptx = getattr(brand_dna, "source_file_path", None)
    
    policy = parse_essence_to_policy(
        brand_id=getattr(brand_dna, "brand_id", 0),
        brand_name=getattr(brand_dna, "brand_name", ""),
        artistic_essence=artistic_essence_dict,
        visual_dna=visual_dna_dict,
        source_pptx_path=source_pptx
    )

    # 2. Configurar Canvas y Budget
    max_full_bleed = max(1, int(total_slides * policy.image_rules.max_background_ratio))
    full_bleed_budget = {"used": 0, "max": max_full_bleed}

    final_manifest = {
        "theme": {
            "primary":        visual_dna_dict["primary_color"],
            "background":     visual_dna_dict["background_color"],
            "font_main":      visual_dna_dict["primary_font"],
        },
        "canvas": {
            "width_inches":  policy.canvas.width_inches,
            "height_inches": policy.canvas.height_inches,
        },
        "slides": []
    }

    # 3. Construir Slides determinísticamente
    for i, slide in enumerate(all_slides):
        slide_type = _infer_slide_type(slide)

        elements, layout = build_slide_elements(
            slide=slide,
            slide_type=slide_type,
            slide_index=i,
            total_slides=total_slides,
            policy=policy,
            visual_dna=visual_dna_dict,
            full_bleed_budget=full_bleed_budget,
        )

        final_manifest["slides"].append({
            "slide_number":    slide.get("slide_number", i + 1),
            "slide_type":      slide_type,
            "layout":          layout,
            "elements":        elements,
            "title":           slide.get("title"),
            "bullets":         slide.get("bullets", []),
            "metric":          slide.get("metric"),
        })

    return final_manifest
