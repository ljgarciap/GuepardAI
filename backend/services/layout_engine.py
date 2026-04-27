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
    DESIGN ARCHITECT v18.0 — SENIOR ART DIRECTOR DRIVEN.
    Analiza slide por slide para evitar colisiones y elegir las mejores imágenes.
    """
    all_slides = content_manifest.get("slides", [])
    total_slides = len(all_slides)

    # 1. Preparar Contexto de Marca
    visual_dna_dict = {
        "primary_color":    getattr(brand_dna, "primary_color", "#0052A3"),
        "secondary_color":  getattr(brand_dna, "secondary_color", "#EE1C2E"),
        "background_color": getattr(brand_dna, "background_color", "#FFFFFF"),
        "primary_font":     getattr(brand_dna, "primary_font", "Arial"),
    }
    
    artistic_essence_dict = {
        "structural_archetypes": getattr(brand_essence, "structural_archetypes", {}),
        "slide_archetypes":      getattr(brand_essence, "slide_archetypes", {}),
        "design_gestures":       getattr(brand_essence, "design_gestures", {}),
        "visual_patterns":       getattr(brand_essence, "visual_patterns", []),
        "visual_strategy":       getattr(brand_essence, "visual_strategy", ""),
    }

    policy = parse_essence_to_policy(
        brand_id=getattr(brand_dna, "brand_id", 0),
        brand_name=getattr(brand_dna, "brand_name", ""),
        artistic_essence=artistic_essence_dict,
        visual_dna=visual_dna_dict,
        force_width=getattr(brand_dna, "slide_width_inches", 21.99),
        force_height=getattr(brand_dna, "slide_height_inches", 12.37)
    )

    # 2. Obtener Biblioteca de Imágenes Disponibles
    # Esto es CRUCIAL para dejar de usar solo 2 imágenes.
    available_assets = []
    if hasattr(brand_dna, "extracted_assets") and brand_dna.extracted_assets:
        for cat in ["photos", "logos", "icons"]:
            for asset in brand_dna.extracted_assets.get(cat, []):
                available_assets.append({
                    "id": asset.get("path"),
                    "tags": asset.get("tags", []),
                    "description": asset.get("description", "")
                })

    # 3. LLM ART DIRECTOR: Planificación Maestra
    # Le pedimos al LLM que analice TODO el contenido y asigne los mejores recursos.
    from database import SessionLocal
    from models import SystemConfig
    db = SessionLocal()
    pref_model = db.query(SystemConfig).filter(SystemConfig.key == 'art_director_model').first()
    model_name = pref_model.value if pref_model else "models/gemini-1.5-flash"
    db.close()

    art_director_prompt = f"""
    You are a Senior Art Director for {getattr(brand_dna, 'brand_name', 'Tesco')}.
    BRAND STRATEGY: {artistic_essence_dict['visual_strategy']}
    PATTERNS: {artistic_essence_dict['visual_patterns']}
    
    TASK: Assign the best images and layout archetypes for each slide.
    AVAILABLE IMAGES: {json.dumps(available_assets[:40])}
    
    CONTENT TO RE-LAYOUT:
    {json.dumps([{ 'i': i, 'title': s.get('title'), 'bullets': s.get('bullets', []) } for i, s in enumerate(all_slides)])}
    
    RULES:
    1. IMAGE VARIETY: Use at least 8-10 different images across the deck.
    2. RELEVANCE: Match image tags with slide keywords.
    3. COLLISION AVOIDANCE: If text is long, reduce font scale or pick 'clean' layouts.
    
    OUTPUT ONLY JSON:
    {{
      "assignments": [
        {{ "i": 0, "layout": "full-bleed | split-right | accent-box", "image_id": "filename", "font_scale": 0.8 }}
      ]
    }}
    """
    
    try:
        planning = generate_json(art_director_prompt, model=model_name)
        assignments = { item['i']: item for item in planning.get("assignments", []) }
    except:
        assignments = {}

    # 4. Construcción Final
    full_bleed_budget = {"used": 0, "max": int(total_slides * 0.3)}
    final_manifest = {
        "theme": { "primary": visual_dna_dict["primary_color"], "background": visual_dna_dict["background_color"], "font_main": visual_dna_dict["primary_font"] },
        "canvas": { "width_inches": policy.canvas.width_inches, "height_inches": policy.canvas.height_inches },
        "slides": []
    }

    for i, slide in enumerate(all_slides):
        plan = assignments.get(i, {})
        # Usamos el plan del director de arte o inferimos si falló
        stype = plan.get("layout", _infer_slide_type(slide))
        
        # Override de imagen semántica
        if plan.get("image_id"):
            slide["assigned_image"] = plan["image_id"]
        
        elements, layout = build_slide_elements(
            slide=slide,
            slide_type=stype,
            slide_index=i,
            total_slides=total_slides,
            policy=policy,
            visual_dna=visual_dna_dict,
            full_bleed_budget=full_bleed_budget,
            font_scale_override=plan.get("font_scale", 1.0)
        )

        final_manifest["slides"].append({
            "slide_number": slide.get("slide_number", i + 1),
            "elements": elements,
            "layout": layout,
            "title": slide.get("title")
        })

    return final_manifest
