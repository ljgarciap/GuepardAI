import os
import time
import json
import base64
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from llm_provider import generate_json, get_system_config
import models
from database import SessionLocal

def _infer_slide_type(slide: dict) -> str:
    num = slide.get("slide_number", 1)
    intent = slide.get("layout_intent", "").lower()
    title = slide.get("title", "").lower()
    if num == 1 or "hero" in intent or "title" in intent: return "title"
    if "metric" in intent or "data" in intent or "grid" in intent or slide.get("metric"): return "data"
    if "quote" in intent or "testimonial" in title: return "image_hero"
    if num >= 14 or "thank you" in title or "conclusion" in title: return "conclusion"
    return "content"

def get_base64_image(raw_path: Optional[str]) -> str:
    """Helper para convertir un asset local en Base64 seguro para HTML."""
    if not raw_path: return ""
    
    # Resolve path relative to /app
    actual_path = raw_path if raw_path.startswith("/") else os.path.join("/app", raw_path)
    
    if os.path.exists(actual_path):
        try:
            with open(actual_path, "rb") as img_f:
                b64_data = base64.b64encode(img_f.read()).decode()
                ext = os.path.splitext(actual_path)[1].lower().replace(".", "")
                if ext == "jpg": ext = "jpeg"
                if not ext: ext = "png"
                mime_type = f"image/{ext}"
                return f"data:{mime_type};base64,{b64_data}"
        except Exception as e:
            print(f"  [ERROR] Encoding failed for {actual_path}: {e}")
    return "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab"

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

def apply_design_policy(content_manifest: dict, brand_dna, brand_essence=None, job_id=None) -> dict:
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
                    "id": asset.get("id"),
                    "tags": asset.get("tags", []),
                    "description": asset.get("description", "")
                })

    # 3. LLM ART DIRECTOR: Planificación Maestra
    # Le pedimos al LLM que analice TODO el contenido y asigne los mejores recursos.
    model_name = get_system_config("art_director_model", "models/gemini-1.5-flash")

    # 3. Director de Arte Senior - Slide by Slide Analysis (v18.7)
    # Buscamos slides de referencia del manual original para máxima fidelidad
    from services.asset_library_service import find_best_assets
    
    # Intentamos encontrar las "slides maestras" del manual original
    reference_slides = find_best_assets(
        db, 
        getattr(brand_dna, "brand_id", brand_dna.id),
        keywords=["slide", "layout", "presentation"],
        category="reference",
        limit=20
    )
    
    art_director_prompt = f"""
    You are a Senior Art Director for {getattr(brand_dna, 'brand_name', 'Tesco')}.
    
    BRAND DNA (STRICT ADHERENCE):
    - Primary Color: {visual_dna_dict['primary_color']}
    - Secondary Color: {visual_dna_dict['secondary_color']}
    - Main Font: {visual_dna_dict['primary_font']}
    
    VISUAL STRATEGY: {artistic_essence_dict['visual_strategy']}
    DESIGN GESTURES: {json.dumps(artistic_essence_dict['design_gestures'])}
    PATTERNS: {artistic_essence_dict['visual_patterns']}
    
    TASK: Assign the best images and layout archetypes for each slide to maximize BRAND FIDELITY.
    AVAILABLE IMAGES: {json.dumps(available_assets[:50])}
    REFERENCE SLIDES FROM MANUAL: {json.dumps([{'id': r.id, 'desc': r.description} for r in reference_slides])}
    
    CONTENT TO RE-LAYOUT:
    {json.dumps([{ 'i': i, 'title': s.get('title'), 'bullets': s.get('bullets', []) } for i, s in enumerate(all_slides)])}
    
    ART DIRECTION RULES:
    1. BRAND COLORS: Use {visual_dna_dict['primary_color']} for headers and important shapes.
    2. IMAGE SELECTION (CRITICAL): Prioritize 'Tesco' branded photos or logos from the AVAILABLE IMAGES. 
    3. NO GENERIC: Avoid using non-branded lifestyle photos if a Tesco-specific asset exists.
    4. FIDELITY: If a 'REFERENCE SLIDE' from the manual matches the content type, use its structure.
    
    OUTPUT ONLY JSON:
    {{
      "assignments": [
        {{ 
          "i": 0, 
          "layout": "full-bleed | split-right | accent-box | title-hero", 
          "image_id": "filename from AVAILABLE IMAGES", 
          "font_scale": 0.9,
          "reference_id": "optional_id_from_manual" 
        }}
      ]
    }}
    """
    
    try:
        planning = generate_json(art_director_prompt, model=model_name)
        assignments = { item['i']: item for item in planning.get("assignments", []) }
    except:
        assignments = {}

    # 4. Construcción Final con Persistencia Granular (v18.5)
    from database import SessionLocal
    from models import PresentationSlide
    db = SessionLocal()
    
    # Limpiamos slides previas si es un re-intento
    db.query(PresentationSlide).filter(PresentationSlide.job_id == job_id).delete()

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
            from models import BrandAsset
            asset_rec = db.query(BrandAsset).get(plan["image_id"])
            if asset_rec:
                slide["assigned_image"] = os.path.basename(asset_rec.local_path)
        
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

        # PERSISTENCIA EN DB (v18.5)
        new_slide = PresentationSlide(
            job_id=job_id,
            slide_number=i + 1,
            title=slide.get("title", "Untitled"),
            content_json=slide,
            layout_slug=layout,
            assigned_image=slide.get("assigned_image"),
            reference_id=plan.get("reference_id"),
            font_scale=plan.get("font_scale", 1.0),
            render_elements=elements,
            planning_json={
                "layout_reasoning": f"Chose {layout} based on {stype} strategy",
                "grammar_logic": elements.get("grammar_type", "standard")
            }
        )
        db.add(new_slide)

        final_manifest["slides"].append({
            "slide_number": i + 1,
            "elements": elements,
            "layout": layout,
            "title": slide.get("title")
        })

    db.commit()
    db.close()
    return final_manifest

def generate_presentation_flow(db: Session, job_id: int, req_data: dict):
    """
    ORQUESTADOR MAESTRO v8.0 (GammaPainter Connected).
    Coordina: Contenido -> Arte -> Pintado con GammaPainter.
    """
    from services.content_service import synthesize_presentation_outline
    from services.art_director_service import plan_presentation_design
    from services.pptx_renderer import render_pptx_from_db

    job = db.query(models.GenerationJob).get(job_id)
    if not job: return

    # Verificar modo de renderer
    renderer_cfg = db.query(models.SystemConfig).filter(
        models.SystemConfig.key == "renderer_mode"
    ).first()
    use_painter = (renderer_cfg and renderer_cfg.value == "painter")

    try:
        # FASE 1: SÍNTESIS DE CONTENIDO
        job.status = "processing"
        job.current_step = "Phase 1/3: Synthesizing strategic content..."
        job.progress = 10
        db.commit()
        if not synthesize_presentation_outline(db, job_id, req_data):
            raise Exception("Failed during Content Synthesis.")

        # FASE 2: DIRECCIÓN DE ARTE
        job.current_step = "Phase 2/3: Planning art direction and asset selection..."
        job.progress = 40
        db.commit()
        if not plan_presentation_design(db, job_id):
            raise Exception("Failed during Art Direction.")

        output_format = req_data.get("output_format", "pptx")
        
        # Construir asset_map global
        asset_map = {}
        assets = db.query(models.BrandAsset).filter(
            (models.BrandAsset.brand_id == job.brand_id) |
            (models.BrandAsset.is_public == 1)
        ).all()
        for a in assets:
            if a.local_path:
                asset_map[os.path.basename(a.local_path)] = a.local_path

        if output_format == "pdf_artistic":
            # ── MODO PDF ARTÍSTICO ──
            from services.artistic_pdf_service import artistic_pdf_service
            from models import BrandVisualDna, PresentationSlide
            
            job.current_step = "Phase 3/3: Rendering Artistic PDF (High-Fidelity)..."
            db.commit()
            
            # Obtener Brand DNA
            brand_dna = db.query(BrandVisualDna).filter(BrandVisualDna.brand_id == job.brand_id).first()
            # Obtener slides procesadas de la DB
            db_slides = db.query(PresentationSlide).filter(PresentationSlide.job_id == job_id).order_by(PresentationSlide.slide_number).all()
            
            # Formatear datos para el template HTML
            slides_for_html = []
            for s in db_slides:
                content = s.content_json
                # Resolve primary image
                img_name = s.assigned_image
                resolved_img = get_base64_image(asset_map.get(img_name)) if img_name else "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab"
                
                # Resolve bullet icon (v10.0 Replit-Grade)
                icon_name = s.bullet_icon
                resolved_icon = get_base64_image(asset_map.get(icon_name)) if icon_name else None

                # Dynamic Layout Selection (v3.1 Artistic)
                chosen_layout = "split"
                grammar_type = content.get("layout_type", "composition_split")
                
                if "hero" in grammar_type: chosen_layout = "hero"
                elif "data" in grammar_type: chosen_layout = "data_grid"
                elif "quote" in grammar_type: chosen_layout = "quote"
                elif "pillars" in grammar_type: chosen_layout = "pillars"
                
                slides_for_html.append({
                    "title": s.title,
                    "subtitle": content.get("subtitle", ""),
                    "metadata": content.get("metadata", {}),
                    "section_label": content.get("section_label", "Executive Insights"),
                    "primary_image": resolved_img,
                    "bullet_icon": resolved_icon,
                    "bullets": content.get("bullets", []),
                    "metrics": content.get("metrics", []),
                    "layout": chosen_layout
                })

            import asyncio
            # Como estamos en un hilo síncrono (add_task), corremos el bucle async para Playwright
            pdf_path = asyncio.run(artistic_pdf_service.generate_pdf(job_id, slides_for_html, brand_dna))
            
            output_filename = os.path.basename(pdf_path)
            download_url = f"/outputs/artistic_pdf/{output_filename}"
            print(f"  [Flow v8.5] ✓ Artistic PDF render complete: {output_filename}")
            
            # Store FULL PATH in DB
            job.pptx_path = pdf_path 
        else:
            # ── MODO PPTX (Legacy/Painter) ──
            output_filename = f"Portfolio_{job_id}_{int(time.time())}.pptx"
            output_path = os.path.join("uploads", output_filename)

            # Renderizar con GammaPainter o renderer legacy
            if use_painter:
                from painter_bridge import render_with_painter
                render_with_painter(db, job_id, asset_map, output_path)
                print(f"  [Flow v8.0] ✓ GammaPainter render complete.")
            else:
                from services.pptx_renderer import render_pptx_from_db
                render_pptx_from_db(job_id, asset_map, output_path)
                print(f"  [Flow v8.0] ✓ Legacy renderer complete.")
            
            download_url = f"/uploads/{output_filename}"
            # Store FULL PATH in DB
            job.pptx_path = output_path

        # FINALIZACIÓN
        job.status = "completed"
        job.current_step = "Portfolio ready."
        job.progress = 100
        job.download_url = download_url
        db.commit()

    except Exception as e:
        import traceback
        print(f"  [Flow v8.0] CRITICAL: {traceback.format_exc()}")
        job.status = "error"
        job.current_step = f"Error: {str(e)}"
        db.commit()
