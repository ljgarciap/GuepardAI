"""
painter_bridge.py — GuepardAI v8.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROPÓSITO: Conectar GammaPainter al pipeline de producción.

CAMBIO EN layout_engine.py — reemplazar la línea:
    render_pptx_from_db(job_id, asset_map, output_path)
POR:
    from services.rendering.painter_bridge import render_with_painter
    render_with_painter(db, job_id, asset_map, output_path)

ESO ES TODO. El resto de este archivo hace el trabajo.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import json
from sqlalchemy.orm import Session
import models

# ══════════════════════════════════════════════════════════════
# MAPA: grammar_type del Art Director → método del GammaPainter
# ══════════════════════════════════════════════════════════════

GRAMMAR_TO_PAINTER = {
    # Grammar types del sistema v3.0
    "strategic_split":      "composition_split",
    "executive_quote":      "composition_quote",
    "impact_number":        "big_metric",
    "section_break":        "composition_hero",    # Fondo de color = hero sin imagen
    "case_study":           "composition_split",   # Split con métricas en bullets
    "two_column":           "composition_grid",
    "cover_hero":           "composition_hero",
    "data_grid":            "paint_data_grid_cards", # v10.0: Unified data cards
    "closing_cta":          "composition_quote",
    "marketing_hero":       "composition_hero",
    "asymmetric_overlay":   "composition_hero",
    "data_grid_cards":      "paint_data_grid_cards",
    "composition_pillars":  "composition_pillars",
    "composition_quote":    "composition_quote",
    "composition_grid":     "composition_grid",
    "big_metric":           "big_metric",

    # Aliases del seed.py
    "split-right":          "composition_split",
    "full-bleed":           "composition_hero",
    "two-column":           "composition_pillars",
    "quote-hero":           "composition_quote",
}


def _resolve_asset_path(asset_source: str, asset_map: dict) -> str | None:
    """
    Resuelve el path real de un asset.
    Acepta: basename, path relativo o path absoluto.
    """
    if not asset_source:
        return None

    # Path absoluto directo
    if os.path.isabs(asset_source) and os.path.exists(asset_source):
        return asset_source

    # Por basename en el asset_map
    basename = os.path.basename(asset_source)
    if basename in asset_map:
        return asset_map[basename]

    # Por path completo en asset_map
    if asset_source in asset_map:
        return asset_map[asset_source]

    # Fallback: si es relativo y existe en uploads/
    relative_path = os.path.join("uploads", os.path.basename(asset_source))
    if os.path.exists(relative_path):
        return os.path.abspath(relative_path)

    return None


def _build_slide_data(slide, asset_map: dict, db: Session) -> dict:
    """
    Convierte un PresentationSlide (DB) al formato que GammaPainter.render_slides() espera.

    Formato esperado por GammaPainter:
    {
        "layout_type": "composition_split",
        "title": "...",
        "bullets": ["..."],
        "metric": "...",        # Para big_metric
        "label": "...",         # Para big_metric (subtítulo del número)
        "tag": "STRATEGY",      # Para la pill-label
        "primary_asset_path": "/abs/path/to/image.jpg"
    }
    """
    content = slide.content_json or {}
    render = slide.render_elements or {}

    # Determinar grammar_type — prioridad: render_elements > content_json > fallback
    grammar_type = (
        render.get("grammar_type") or
        content.get("layout_type") or
        "strategic_split"
    )

    # Mapear al método del Painter
    if content.get("metrics") and grammar_type not in ("composition_hero", "composition_quote", "big_metric", "strategic_split"):
        grammar_type = "data_grid_cards"
        
    layout_type = GRAMMAR_TO_PAINTER.get(grammar_type, "composition_split")

    # Resolver path del asset principal
    primary_asset_path = None
    elements = render.get("elements", [])
    for el in elements:
        if el.get("type") == "image" and el.get("role") in ("main", "supporting", "background", "person_bleed"):
            src = el.get("source") or el.get("path", "")
            resolved = _resolve_asset_path(str(src), asset_map)
            if resolved:
                primary_asset_path = resolved
                break

    # Fallback 1: buscar en content_json
    if not primary_asset_path:
        src = content.get("image_path") or content.get("primary_asset_path")
        if src:
            primary_asset_path = _resolve_asset_path(str(src), asset_map)

    # Fallback 2: buscar en slide.assigned_image (v8.1)
    if not primary_asset_path and getattr(slide, "assigned_image", None):
        img_id = slide.assigned_image
        # Si es un ID numérico, buscar el path real en la DB
        if str(img_id).isdigit():
            asset_rec = db.query(models.BrandAsset).get(int(img_id))
            if asset_rec and asset_rec.local_path:
                primary_asset_path = _resolve_asset_path(os.path.basename(asset_rec.local_path), asset_map)
        else:
            primary_asset_path = _resolve_asset_path(str(img_id), asset_map)

    # Construir bullets — prioridad: render_elements text body > content_json bullets
    bullets = content.get("bullets", [])
    for el in elements:
        if el.get("role") == "body" and el.get("content"):
            raw = el["content"]
            # El body puede estar como "• bullet1\n• bullet2" o como lista
            if isinstance(raw, str) and "\n" in raw:
                bullets = [b.lstrip("•– ").strip() for b in raw.split("\n") if b.strip()]
            elif isinstance(raw, list):
                bullets = raw
            break

    # Determinar tag (sección) para la pill-label
    tag_map = {
        "composition_hero":     "INTRODUCTION",
        "composition_quote":    "TESTIMONIAL",
        "big_metric":           "INSIGHT",
        "composition_grid":     "STRATEGY",
        "composition_pillars":  "PILLARS",
        "composition_split":    "STRATEGY",
    }
    tag = content.get("section_label") or tag_map.get(layout_type, "STRATEGY")

    # v12.0: Designer Override (Custom Canvas)
    planning = slide.planning_json or {}
    ad_planning = planning.get("art_director", {})
    
    if ad_planning.get("layout_override"):
        grammar_type = ad_planning["layout_override"]
        if grammar_type == "custom_canvas":
            layout_type = "custom_canvas"

    return {
        "layout_type":          layout_type,
        "title":                slide.title or "",
        "bullets":              bullets,
        "metric":               content.get("metric", ""),
        "label":                content.get("label", ""),
        "tag":                  tag.upper(),
        "primary_asset_path":   primary_asset_path,
        # Metadata extra para tipos especiales
        "grammar_type":         grammar_type,
        "slide_number":         slide.slide_number,
        "metrics":              content.get("metrics", []),
        "metadata":             content.get("metadata", {}),
        "elements":             ad_planning.get("canvas_elements", [])
    }


def render_with_painter(db: Session, job_id: int, asset_map: dict, output_path: str) -> str:
    """
    FUNCIÓN PRINCIPAL — reemplaza render_pptx_from_db().

    Carga los slides desde DB, construye el content_json para GammaPainter,
    y delega el renderizado a los métodos paint_X() del Painter.

    Retorna el output_path del archivo generado.
    """
    import models
    from services.rendering.painter import GammaPainter

    print(f"  [PainterBridge] Starting GammaPainter render for Job {job_id}...")

    # 1. Cargar datos necesarios
    job = db.query(models.GenerationJob).get(job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")

    dna_record = db.query(models.BrandVisualDna).filter(
        models.BrandVisualDna.brand_id == job.brand_id
    ).first()

    if not dna_record:
        raise ValueError(f"No BrandVisualDna found for brand_id {job.brand_id}")

    # 2. Enriquecer el brand_style con datos que GammaPainter necesita
    #    (GammaPainter espera un objeto con atributos, no un dict)
    _patch_dna_for_painter(dna_record, db, job, asset_map)

    # 3. Branding Metadata
    logo_path = None
    if job.brand_id:
        brand = db.query(models.Brand).filter(models.Brand.id == job.brand_id).first()
        if brand and brand.logo_path:
            logo_path = _resolve_asset_path(brand.logo_path, asset_map)
            
            # v16.7: Smart Fallback (Anti-Hardcoding)
            # If the path doesn't exist, search for it in uploads
            if logo_path and not os.path.exists(logo_path):
                print(f"  [PainterBridge] Logo path not found: {logo_path}. Searching in uploads...")
                brand_slug = job.client_name.lower() if job.client_name else "client"
                uploads_dir = os.path.abspath("uploads")
                if os.path.exists(uploads_dir):
                    for f in os.listdir(uploads_dir):
                        if "logo" in f.lower() and brand_slug in f.lower():
                            logo_path = os.path.join(uploads_dir, f)
                            print(f"  [PainterBridge] Dynamic Logo Found: {logo_path}")
                            break
            
            # Absolute path enforcement
            if logo_path and not os.path.isabs(logo_path):
                logo_path = os.path.abspath(logo_path)
    
    agency_name = db.query(models.SystemConfig).filter(models.SystemConfig.key == "agency_name").first()
    agency_logo = db.query(models.SystemConfig).filter(models.SystemConfig.key == "agency_logo_path").first()
    agency_email = db.query(models.SystemConfig).filter(models.SystemConfig.key == "agency_contact_email").first()
    
    # Resolve agency logo to absolute path too
    agency_logo_path = agency_logo.value if agency_logo else "assets/agency/L-founders_logo.png"
    if agency_logo_path and not os.path.isabs(agency_logo_path):
        agency_logo_path = os.path.abspath(agency_logo_path)

    agency_branding = {
        "name": agency_name.value if agency_name else "L - Founders of Loyalty",
        "logo_path": agency_logo_path,
        "client_name": job.client_name or "Client",
        "email": agency_email.value if agency_email else "contact@l-founders.com"
    }

    # 4. Cargar slides ordenados
    slides = db.query(models.PresentationSlide).filter(
        models.PresentationSlide.job_id == job_id
    ).order_by(models.PresentationSlide.slide_number.asc()).all()

    if not slides:
        raise ValueError(f"No slides found for job_id {job_id}")

    print(f"  [PainterBridge] Found {len(slides)} slides. Building content_json...")

    # 5. Construir content_json con reglas de variedad
    slide_data_list = []
    grammar_type_history = []

    for i, slide in enumerate(slides):
        data = _build_slide_data(slide, asset_map, db)
        data["is_last"] = (i == len(slides) - 1)
        data["logo_path"] = logo_path
        data["agency_branding"] = agency_branding

        # REGLA DE VARIEDAD: si el mismo layout se repite 3 veces seguidas, forzar cambio
        layout = data["layout_type"]
        if grammar_type_history[-3:].count(layout) >= 3:
            alternatives = ["composition_pillars", "big_metric", "composition_quote"]
            bullets = data.get("bullets", [])
            metric_candidates = [b for b in bullets if any(c.isdigit() for c in b)]

            if metric_candidates:
                data["layout_type"] = "big_metric"
                # Extraer métrica del primer bullet con número
                import re
                nums = re.findall(r'[\d,\.%\+\-]+', metric_candidates[0])
                data["metric"] = nums[0] if nums else ""
                data["label"] = metric_candidates[0]
            else:
                data["layout_type"] = "composition_pillars"

            print(f"  [PainterBridge] Variety override on slide {slide.slide_number}: "
                  f"{layout} → {data['layout_type']}")

        grammar_type_history.append(data["layout_type"])
        slide_data_list.append(data)

    # 5. Obtener Logo de Marca y Branding de Agencia (v24.0)
    brand = db.query(models.Brand).get(job.brand_id)
    logo_path = None
    if brand and brand.logo_path:
        logo_path = _resolve_asset_path(brand.logo_path, asset_map)
    
    content_json = {
        "slides": slide_data_list,
        "logo_path": logo_path,
        "agency_branding": agency_branding
    }

    # 5. Estadísticas de variedad
    from collections import Counter
    variety = Counter(d["layout_type"] for d in slide_data_list)
    print(f"  [PainterBridge] Layout variety: {dict(variety)}")

    # 6. Instanciar GammaPainter y renderizar
    painter = GammaPainter(dna_record)
    print(f"  [DEBUG] Painter Type: {type(painter)}")
    print(f"  [DEBUG] Painter Methods: {dir(painter)}")
    
    # Check if method exists to prevent crash and show truth
    if not hasattr(painter, "render_slides"):
        print(f"  [CRITICAL] render_slides MISSING in this instance!")
    
    painter.render_slides(content_json)

    # 7. Guardar y retornar
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    painter.save(output_path)

    print(f"  [PainterBridge] ✓ PPTX saved to {output_path}")
    return output_path


def _patch_dna_for_painter(dna_record, db, job, asset_map: dict):
    """
    GammaPainter accede a dna_record como objeto con atributos.
    Algunos atributos que usa pueden no existir o estar en formato incorrecto.
    Este patcher los garantiza sin modificar el modelo de DB.
    """
    import models

    # visual_strategy — GammaPainter.strategy usa esto para vision_insights
    if not getattr(dna_record, "visual_strategy", None):
        # Intentar cargar desde brand_artistic_essence
        essence = db.query(models.BrandArtisticEssence).filter(
            models.BrandArtisticEssence.brand_id == job.brand_id
        ).first()
        if essence:
            dna_record.visual_strategy = {
                "vision_insights": {
                    "archetypes": essence.slide_archetypes or [],
                    "design_gestures": essence.design_gestures or {},
                },
                "technical_metrics": {"kerning": -0.05, "padding_percent": 0.1},
            }
        else:
            dna_record.visual_strategy = {
                "vision_insights": {"archetypes": [], "design_gestures": {}},
                "technical_metrics": {"kerning": -0.05, "padding_percent": 0.1},
            }

    # font_family — alias de primary_font
    if not getattr(dna_record, "font_family", None):
        dna_record.font_family = getattr(dna_record, "primary_font", "Arial") or "Arial"

    # background_color — default blanco
    if not getattr(dna_record, "background_color", None):
        dna_record.background_color = "#FFFFFF"

    # extracted_assets — GammaPainter.asset_bank lo usa para su propio image picker
    # Aseguramos que sea una lista de paths absolutos de assets de marca
    if not getattr(dna_record, "extracted_assets", None):
        assets = db.query(models.BrandAsset).filter(
            models.BrandAsset.brand_id == job.brand_id,
            models.BrandAsset.category.in_(["lifestyle_photos", "images", "structural_images"])
        ).all()
        dna_record.extracted_assets = [
            os.path.basename(a.local_path)
            for a in assets
            if a.local_path and os.path.exists(a.local_path)
        ]
