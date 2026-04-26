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

def orchestrate_visual_coherence(content_manifest: dict, brand_dna, brand_essence=None) -> dict:
    return content_manifest

def apply_design_policy(content_manifest: dict, brand_dna, brand_essence=None) -> dict:
    """
    DESIGN ARCHITECT v15.0 — PURE PARAMETRIC (Metric Support Included).
    """
    all_slides = content_manifest.get("slides", [])
    total_slides = len(all_slides)

    # DNA Visual info
    primary_color    = getattr(brand_dna, "primary_color", "#333333")
    secondary_color  = getattr(brand_dna, "secondary_color", "#666666")
    background_color = getattr(brand_dna, "background_color", "#FFFFFF")
    primary_font     = getattr(brand_dna, "primary_font", "Arial")
    secondary_font   = getattr(brand_dna, "secondary_font", None) or primary_font
    text_main_color  = getattr(brand_dna, "text_main_color", "#000000")
    extracted_assets = getattr(brand_dna, "extracted_assets", []) or []

    # Artistic Essence
    design_gestures = getattr(brand_essence, "design_gestures", {}) if brand_essence else {}
    composition     = getattr(brand_essence, "composition_rules", {}) if brand_essence else {}

    max_full_bleed = max(2, total_slides // 3)
    full_bleed_count = 0

    final_manifest = {
        "theme": {
            "primary": primary_color, "secondary": secondary_color,
            "background": background_color, "accent": secondary_color,
            "font_main": primary_font, "font_secondary": secondary_font,
        },
        "slides": []
    }

    for i, slide in enumerate(all_slides):
        slide_num = slide.get("slide_number", i + 1)
        slide_type = _infer_slide_type(slide)
        
        if slide_type in ["title", "image_hero"] and full_bleed_count >= max_full_bleed:
            slide_type = "content"
        if slide_type in ["title", "image_hero"]:
            full_bleed_count += 1

        layout = "full-bleed" if slide_type in ["title", "image_hero"] else "split-left"
        if slide_type == "conclusion": layout = "centered"

        archetype = {
            "layout": layout,
            "style": "brand-faithful",
            "corner_radius": "rounded" if design_gestures.get("corner_style") == "rounded" else "sharp"
        }

        elements = _build_slide_elements(
            slide=slide, slide_type=slide_type, archetype=archetype,
            primary_color=primary_color, secondary_color=secondary_color,
            background_color=background_color, primary_font=primary_font,
            secondary_font=secondary_font, text_main_color=text_main_color,
            available_assets=extracted_assets, slide_num=slide_num,
            design_gestures=design_gestures
        )

        final_manifest["slides"].append({
            "slide_number": slide_num, "slide_type": slide_type,
            "archetype": archetype, "elements": elements,
            "title": slide.get("title"), "bullets": slide.get("bullets", []),
            "metric": slide.get("metric"),
            "image_narrative": slide.get("image_narrative", ""),
        })

    return final_manifest

def _build_slide_elements(
    slide, slide_type, archetype, primary_color, secondary_color, 
    background_color, primary_font, secondary_font, text_main_color,
    available_assets, slide_num, design_gestures
) -> list:
    elements = []
    is_impact = (archetype["layout"] == "full-bleed")
    corner_style = design_gestures.get("corner_style", "rounded")
    
    # ── BASE ──
    elements.append({"type": "background_color", "color": background_color, "geometry": {"left": 0, "top": 0, "width": 100, "height": 100}})
    
    # ── DECOR ──
    if not is_impact:
        elements.append({
            "type": "shape", "role": "decor", "shape_type": "rectangle",
            "geometry": {"left": 61, "top": 0, "width": 39, "height": 100},
            "style": {"color": secondary_color, "opacity": 0.03}
        })
        elements.append({
            "type": "shape", "role": "accent", "shape_type": "rectangle",
            "geometry": {"left": 61, "top": 0, "width": 0.2, "height": 100},
            "style": {"color": primary_color, "opacity": 1.0}
        })

    # ── IMAGES ──
    if is_impact:
        elements.append({
            "type": "image", "role": "background", "source": slide_num,
            "geometry": {"left": 0, "top": 0, "width": 100, "height": 100}
        })
        ov_opacity = design_gestures.get("overlay_opacity", 0.6)
        elements.append({
            "type": "shape", "role": "overlay", "geometry": {"left": 0, "top": 0, "width": 100, "height": 100},
            "style": {"color": "#000000", "opacity": ov_opacity}
        })
    else:
        elements.append({
            "type": "image", "role": "supporting", "source": slide_num,
            "geometry": {"left": 66, "top": 28, "width": 28, "height": 44},
            "style": {"corner_style": corner_style}
        })

    # ── TEXT ──
    title_text = slide.get("title", "")
    title_color = _get_contrast_color(background_color if not is_impact else "#000000", primary_color, "#FFFFFF")
    body_color = _get_contrast_color(background_color if not is_impact else "#000000", text_main_color, "#FFFFFF")
    
    # --- ADAPTIVE VERTICAL SPACING (v15.1) ---
    # Si el título es largo (> 40 caracteres), bajamos el cuerpo de texto
    title_height = 12
    body_top = 35
    if len(title_text) > 40:
        title_height = 18
        body_top = 42
    if len(title_text) > 75:
        title_height = 24
        body_top = 48

    elements.append({
        "type": "text", "role": "title", "content": title_text,
        "geometry": {"left": 7, "top": 12, "width": 50 if not is_impact else 86, "height": title_height},
        "style": {"font": primary_font, "size": 32, "color": title_color, "bold": True}
    })
    
    bullets = slide.get("bullets", [])
    if bullets:
        bullet_text = "\n".join([f"• {b}" for b in bullets])
        
        # --- DYNAMIC BODY SCALING (v15.3) ---
        # Si hay mucho texto, bajamos la fuente agresivamente
        body_size = 18
        if len(bullet_text) > 300: body_size = 14
        if len(bullet_text) > 500: body_size = 12
        if len(bullet_text) > 800: body_size = 10

        elements.append({
            "type": "text", "role": "bullets", "content": bullet_text,
            "geometry": {"left": 7, "top": body_top, "width": 50 if not is_impact else 86, "height": 80 - body_top},
            "style": {"font": secondary_font, "size": body_size, "color": body_color}
        })

    # ── METRIC (STRATEGIC VALUE) ──
    metric = slide.get("metric")
    if metric:
        metric_color = _get_contrast_color(background_color if not is_impact else "#000000", primary_color, "#FFFFFF")
        elements.append({
            "type": "text", "role": "metric", "content": metric,
            "geometry": {"left": 7, "top": 88, "width": 86, "height": 7},
            "style": {"font": primary_font, "size": 14, "color": metric_color, "bold": True, "align": "left"}
        })

    # Logo
    logos = available_assets if isinstance(available_assets, list) else available_assets.get("logos", [])
    if logos:
        elements.append({
            "type": "logo", "source": logos[0],
            "geometry": {"left": 88, "top": 3, "width": 8, "height": 5}
        })

    return elements
