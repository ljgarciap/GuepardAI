import json
import os
from typing import Optional, List, Dict
import os
from llm_provider import generate_json


# Arquetipos de layout por defecto (cuando no hay Esencia Artística)
DEFAULT_ARCHETYPES = {
    "title":      {"layout": "full-bleed", "image_treatment": "full-bleed-background", "accent": "none"},
    "content":    {"layout": "split-left", "image_treatment": "supporting-right", "accent": "vertical-line"},
    "data":       {"layout": "split-left", "image_treatment": "absent", "accent": "horizontal-bar"},
    "image_hero": {"layout": "full-bleed", "image_treatment": "full-bleed-overlay-dark", "accent": "none"},
    "conclusion": {"layout": "centered", "image_treatment": "full-bleed-background", "accent": "none"},
}


def _infer_slide_type(slide: dict) -> str:
    """Infiere el tipo de slide basado en su contenido."""
    num = slide.get("slide_number", 1)
    intent = slide.get("layout_intent", "").lower()
    title = slide.get("title", "").lower()
    bullets = slide.get("bullets", [])

    if num == 1 or "hero" in intent or "title" in intent:
        return "title"
    if "metric" in intent or "data" in intent or "grid" in intent or slide.get("metric"):
        return "data"
    if "quote" in intent or "testimonial" in title:
        return "image_hero"
    if num >= 14 or "thank you" in title or "gracias" in title or "conclusion" in title:
        return "conclusion"
    return "content"


def _get_contrast_color(hex_bg: str, brand_primary: str, brand_text: str) -> str:
    """Calcula si usar color de marca o blanco según el fondo."""
    hex_bg = str(hex_bg).lstrip('#')
    if len(hex_bg) != 6: return brand_text
    try:
        r, g, b = int(hex_bg[0:2], 16), int(hex_bg[2:4], 16), int(hex_bg[4:6], 16)
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return "#FFFFFF" if luminance < 0.5 else brand_primary
    except: return brand_text

def orchestrate_visual_coherence(content_manifest: dict, brand_dna, brand_essence=None) -> dict:
    """Asigna los mejores assets visuales a cada slide según el contexto."""
    print("[Curator] Ensuring Semantic & Visual Alignment...")
    extracted = getattr(brand_dna, "extracted_assets", {})
    # Manejar formatos de assets (dict vs list)
    photos = []
    if isinstance(extracted, dict):
        photos = extracted.get("photos", [])
    elif isinstance(extracted, list):
        photos = extracted

    if not photos: return content_manifest

    for slide in content_manifest.get("slides", []):
        title = (slide.get("title") or "").lower()
        narrative = (slide.get("image_narrative") or "").lower()
        
        # Búsqueda semántica simple
        best_match = None
        for photo in photos:
            desc = (photo.get("description") or "").lower() if isinstance(photo, dict) else ""
            if desc and (desc in narrative or any(w in title for w in desc.split() if len(w) > 4)):
                best_match = photo
                break
        
        if best_match:
            slide["selected_asset"] = best_match.get("path") if isinstance(best_match, dict) else best_match
        else:
            # Fallback rotativo
            idx = (slide.get("slide_number", 0) - 1) % len(photos)
            p = photos[idx]
            slide["selected_asset"] = p.get("path") if isinstance(p, dict) else p
            
    return content_manifest

def apply_design_policy(content_manifest: dict, brand_dna, brand_essence=None) -> dict:
    """
    DESIGN ARCHITECT v4.0 — Consume BrandVisualDna + BrandArtisticEssence.
    Asigna layout, gestos y directivas de diseño a cada slide del manifest.
    """
    all_slides = content_manifest.get("slides", [])

    # Extraer info de DNA Visual
    primary_color    = getattr(brand_dna, "primary_color", "#333333")
    secondary_color  = getattr(brand_dna, "secondary_color", "#666666")
    background_color = getattr(brand_dna, "background_color", "#FFFFFF")
    # PRIORITIZE BRAND COLORS: Use secondary as default accent for better alignment
    accent_color     = secondary_color 
    primary_font     = getattr(brand_dna, "primary_font", "Arial")
    secondary_font   = getattr(brand_dna, "secondary_font", None) or primary_font
    text_main_color  = getattr(brand_dna, "text_main_color", "#000000")
    extracted_assets = getattr(brand_dna, "extracted_assets", []) or []

    # Extraer info de Esencia Artística
    archetypes       = {}
    design_gestures  = {}
    composition      = {}
    art_note         = ""

    if brand_essence:
        structural      = getattr(brand_essence, "structural_archetypes", {}) or {}
        design_gestures = getattr(brand_essence, "design_gestures", {}) or {}
        composition     = getattr(brand_essence, "composition_rules", {}) or {}
        art_note        = getattr(brand_essence, "art_direction_note", "") or ""

    # Fusionar con defaults
    for k, v in DEFAULT_ARCHETYPES.items():
        if k not in archetypes:
            archetypes[k] = v

    print(f"[LayoutEngine v4] Procesando {len(all_slides)} slides con esencia artística "
          f"{'ACTIVA' if brand_essence else 'NO DISPONIBLE'}...", flush=True)

    final_manifest = {
        "theme": {
            "primary":          primary_color,
            "secondary":        secondary_color,
            "background":       background_color,
            "accent":           accent_color,
            "font_main":        primary_font,
            "font_secondary":   secondary_font,
            "design_gestures":  design_gestures,
            "composition":      composition,
            "art_note":         art_note,
        },
        "slides": []
    }

    for i, slide in enumerate(all_slides):
        slide_num  = slide.get("slide_number", i + 1)
        slide_type = _infer_slide_type(slide)
        
        # PARAMETRIC ARCHETYPE: No more hardcoded defaults
        archetype = {
            "layout": "parametric",
            "image_treatment": "supporting-right" if slide_type == "content" else "full-bleed-overlay-dark",
            "accent": "none"
        }

        # Construir elementos
        elements = _build_slide_elements(
            slide=slide,
            slide_type=slide_type,
            archetype=archetype,
            design_gestures=design_gestures,
            composition=composition,
            primary_color=primary_color,
            secondary_color=secondary_color,
            background_color=background_color,
            accent_color=accent_color,
            primary_font=primary_font,
            secondary_font=secondary_font,
            text_main_color=text_main_color,
            available_assets=extracted_assets,
            logo_geo=_logo_geometry(composition.get("logo_position", "top-right")),
            slide_num=slide_num,
            brand_essence=brand_essence
        )

        final_manifest["slides"].append({
            "slide_number":   slide_num,
            "slide_type":     slide_type,
            "archetype":      archetype,
            "elements":       elements,
            "title":          slide.get("title"),
            "bullets":        slide.get("bullets", []),
            "metric":         slide.get("metric"),
            "image_narrative": slide.get("image_narrative", ""),
        })

    return final_manifest


def _build_slide_elements(
    slide, slide_type, archetype, design_gestures, composition,
    primary_color, secondary_color, background_color, accent_color,
    primary_font, secondary_font, text_main_color,
    available_assets, logo_geo, slide_num, brand_essence=None
) -> list:
    elements = []
    structural = getattr(brand_essence, "structural_archetypes", {}) if brand_essence else {}
    gestures   = getattr(brand_essence, "design_gestures", {}) if brand_essence else {}
    
    # ── PARAMETRIC COORDINATES ──
    title_top    = structural.get("title_top", 10)
    title_h      = structural.get("title_height", 15)
    margin_left  = structural.get("margin_left", 5)
    content_y    = max(structural.get("content_start_y", 30), title_top + title_h + 5)
    
    # ── DESIGN PARAMETERS ──
    accent_type   = gestures.get("accent_geometry", "none")
    column_grid   = structural.get("column_grid", "1-column")
    bullet_symbol = structural.get("bullet_symbol", "•")

    # ── CONTRAST DETECTION ──
    is_impact = slide_type in ["title", "image_hero"]
    current_bg  = "#000000" if is_impact else background_color
    title_color = _get_contrast_color(current_bg, primary_color, "#FFFFFF")
    body_color  = _get_contrast_color(current_bg, text_main_color, "#FFFFFF")

    # ── BACKGROUND & IMAGES ──
    elements.append({"type": "background_color", "color": background_color, "geometry": {"left": 0, "top": 0, "width": 100, "height": 100}})
    
    if is_impact:
        elements.append({
            "type": "image", "role": "background", "source": slide_num,
            "geometry": {"left": 0, "top": 0, "width": 100, "height": 100}
        })
        elements.append({
            "type": "shape", "role": "overlay",
            "geometry": {"left": 0, "top": 0, "width": 100, "height": 45},
            "style": {"color": "#000000", "opacity": gestures.get("overlay_opacity", 0.4)}
        })
    else:
        # PURE PARAMETRIC ACCENT: Only draw if the DB says so
        if accent_type == "vertical-line-left":
            elements.append({
                "type": "shape", "role": "accent", "shape_type": "rectangle",
                "geometry": {"left": 0, "top": 0, "width": 1.5, "height": 100},
                "style": {"color": secondary_color, "opacity": 1.0}
            })
        
        if slide_type == "content":
            elements.append({
                "type": "image", "role": "supporting", "source": slide_num,
                "geometry": {"left": 65, "top": 20, "width": 30, "height": 60}
            })

    # ── TEXT CONTENT ──
    # Title with potential 'Red Dot' or 'Pill Banner' treatment
    title_text = slide.get("title", "")
    has_red_dot = (accent_type == "red-dot")
    has_pill_banner = (accent_type == "pill-banners")
    
    if has_red_dot and title_text:
        title_text = f"{title_text.rstrip('.')}." # Ensure single dot, we will color it red in renderer if possible or just handle it here

    if has_pill_banner:
        # Draw the 'Pill' shape behind the title
        elements.append({
            "type": "shape", "role": "banner", "shape_type": "rounded_rectangle",
            "geometry": {"left": margin_left - 1, "top": title_top - 1, "width": 50, "height": title_h + 2},
            "style": {"color": primary_color, "opacity": 1.0}
        })
        title_color = "#FFFFFF" # Contrast for the banner

    elements.append({
        "type": "text", "role": "title", "content": title_text,
        "geometry": {"left": margin_left, "top": title_top, "width": 90 - margin_left, "height": title_h},
        "style": {"font": primary_font, "size": 44 if slide_type == "title" else 36, "color": title_color, "bold": True}
    })
    
    # PARAMETRIC UNDERLINE: Only if specified
    if accent_type == "title-underline":
        elements.append({
            "type": "shape", "role": "accent", "shape_type": "rectangle",
            "geometry": {"left": margin_left, "top": title_top + title_h - 2, "width": 10, "height": 0.5},
            "style": {"color": secondary_color, "opacity": 1.0}
        })

    # Content Area: Pure Parametric Grid
    bullets = slide.get("bullets", [])
    if bullets:
        bullet_text = "\n".join([f"{bullet_symbol} {b}" for b in bullets])
        
        if column_grid == "2-column" and len(bullets) > 3:
            mid = (len(bullets) + 1) // 2
            elements.append({
                "type": "text", "role": "bullets", "content": "\n".join([f"{bullet_symbol} {b}" for b in bullets[:mid]]),
                "geometry": {"left": margin_left, "top": content_y, "width": 30, "height": 60},
                "style": {"font": secondary_font, "size": 16, "color": body_color}
            })
            elements.append({
                "type": "text", "role": "bullets", "content": "\n".join([f"{bullet_symbol} {b}" for b in bullets[mid:]]),
                "geometry": {"left": margin_left + 35, "top": content_y, "width": 30, "height": 60},
                "style": {"font": secondary_font, "size": 16, "color": body_color}
            })
        else:
            elements.append({
                "type": "text", "role": "bullets", "content": bullet_text,
                "geometry": {"left": margin_left, "top": content_y, "width": 55 if not is_impact else 80, "height": 60},
                "style": {"font": secondary_font, "size": 18, "color": body_color}
            })

    # Logo
    logos = available_assets.get("logos", []) if isinstance(available_assets, dict) else available_assets
    if logos:
        elements.append({"type": "logo", "source": logos[0], "geometry": logo_geo})

    return elements

    # Logo
    logos = available_assets.get("logos", []) if isinstance(available_assets, dict) else available_assets
    if logos:
        elements.append({"type": "logo", "source": logos[0], "geometry": logo_geo})

    return elements

    # Logo
    logos = available_assets.get("logos", []) if isinstance(available_assets, dict) else available_assets
    if logos:
        elements.append({"type": "logo", "source": logos[0], "geometry": logo_geo})

    return elements

def _logo_geometry(position: str) -> dict:
    positions = {
        "top-right":    {"left": 88, "top": 3,  "width": 10, "height": 7},
        "top-left":     {"left": 2,  "top": 3,  "width": 10, "height": 7},
        "bottom-right": {"left": 88, "top": 90, "width": 10, "height": 7},
        "bottom-left":  {"left": 2,  "top": 90, "width": 10, "height": 7},
    }
    return positions.get(position, positions["top-right"])

    # ── IMPACT GRID (3 COLUMNS) ──
    if layout == "impact-grid":
        # Overwrite all elements for a 3-column grid structure
        elements = []
        # Add background / overlays as usual... (omitted for brevity, keep existing logic)
        
        # 1. Title Bar
        elements.append({
            "type": "text", "role": "title", "content": title,
            "geometry": {"left": margin_left, "top": title_top, "width": 76, "height": 10},
            "style": {"font": primary_font, "size": 36, "color": primary_color, "bold": True}
        })
        
        # 2. Grid Columns
        col_w = 22
        for idx, bullet in enumerate(bullets[:3]): # Max 3 for the grid
            elements.append({
                "type": "text", "role": "grid-item", "content": bullet,
                "geometry": {"left": margin_left + (idx * 28), "top": current_top + 5, "width": col_w, "height": 40},
                "style": {"font": secondary_font, "size": 18, "color": "#333333", "align": "center"}
            })
        
        return elements
    
    return elements


def _title_geometry(layout: str, gravity: str, slide_type: str) -> dict:
    """Geometría del título según layout."""
    if slide_type == "title":
        return {
            "geometry": {"left": 5, "top": 10, "width": 90, "height": 30},
            "size": 48, # Slightly smaller base for title slides
        }
    if "full-bleed" in layout:
        return {
            "geometry": {"left": 12, "top": 25, "width": 76, "height": 30},
            "size": 44,
        }
    # split-left
    return {
        "geometry": {"left": 12, "top": 12, "width": 42, "height": 22},
        "size": 36,
    }


def _bullets_geometry(layout: str, gravity: str, slide_type: str) -> dict:
    """Geometría de los bullets según layout."""
    if "full-bleed" in layout or slide_type == "title":
        return {
            "geometry": {"left": 12, "top": 65, "width": 76, "height": 28},
            "size": 18,
        }
    # split-left
    return {
        "geometry": {"left": 12, "top": 38, "width": 42, "height": 55},
        "size": 16,
    }
