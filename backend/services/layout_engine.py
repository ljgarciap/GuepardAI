import os
import time
import json
from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from llm_provider import generate_json
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
                    "id": asset.get("path"),
                    "tags": asset.get("tags", []),
                    "description": asset.get("description", "")
                })

    # 3. LLM ART DIRECTOR: Planificación Maestra
    # Le pedimos al LLM que analice TODO el contenido y asigne los mejores recursos.
    from database import SessionLocal
    from models import SystemConfig
    db = SessionLocal()
    pref_model = db.query(models.SystemConfig).filter(models.SystemConfig.key == 'art_director_model').first()
    model_name = pref_model.value if pref_model else "models/gemini-2.5-flash"
    db.close()

    # 3. Director de Arte Senior - Análisis Slide a Slide (v18.7)
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
    2. IMAGE SELECTION: Choose images that match the semantic content. If it's a "Tesco" slide, use Tesco logos or official photos from the library.
    3. LAYOUT VARIETY: Use at least 8-10 different images. Avoid text-only slides if an image is available.
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

        # PERSISTENCIA EN DB (v18.5)
        new_slide = PresentationSlide(
            job_id=job_id,
            slide_number=i + 1,
            title=slide.get("title", "Untitled"),
            content_json=slide,
            layout_slug=layout,
            assigned_image=slide.get("assigned_image"),
            reference_id=plan.get("reference_id"), # Inyectamos la referencia (v18.7)
            font_scale=plan.get("font_scale", 1.0),
            render_elements=elements
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
    ORQUESTADOR MAESTRO v23.0 (Servicios Aislados).
    Coordina el flujo persistente: Contenido -> Arte -> Geometría -> Pintado.
    """
    from services.content_service import synthesize_presentation_outline
    from services.art_director_service import plan_presentation_design
    from services.geometry_service import calculate_presentation_geometry
    from services.pptx_renderer import render_pptx_from_db
    
    job = db.query(models.GenerationJob).get(job_id)
    if not job: return
    
    # Asegurar que el job tenga el style_id si es posible (MVP fallback)
    # style_slug = req_data.get("style_filename")
    
    try:
        # FASE 1: SÍNTESIS DE CONTENIDO (Persistente)
        job.status = "processing"
        job.current_step = "Phase 1/4: Synthesizing strategic content..."
        job.progress = 10
        db.commit()
        if not synthesize_presentation_outline(db, job_id, req_data):
            raise Exception("Failed during Content Synthesis.")

        # FASE 2: DIRECCIÓN DE ARTE (Persistente)
        job.current_step = "Phase 2/4: Planning art direction and tiered asset selection..."
        job.progress = 40
        db.commit()
        if not plan_presentation_design(db, job_id):
            raise Exception("Failed during Art Direction.")

        # FASE 3: CÁLCULO GEOMÉTRICO (Persistente)
        job.current_step = "Phase 3/4: Calculating precision geometry and canvas mapping..."
        job.progress = 70
        db.commit()
        if not calculate_presentation_geometry(db, job_id):
            raise Exception("Failed during Geometry Calculation.")

        # FASE 4: RENDERIZADO FINAL (Reactivo)
        job.current_step = "Phase 4/4: Painting final PPTX portfolio..."
        job.progress = 90
        db.commit()
        
        output_filename = f"Portfolio_{job_id}_{int(time.time())}.pptx"
        output_path = os.path.join("uploads", output_filename)
        
        # Mapa de activos (logos, fotos) - Jerarquía global para el renderer
        asset_map = {}
        assets = db.query(models.BrandAsset).filter(
            (models.BrandAsset.brand_id == job.brand_id) | (models.BrandAsset.is_public == 1)
        ).all()
        for a in assets:
            asset_map[os.path.basename(a.local_path)] = a.local_path
            
        render_pptx_from_db(job_id, asset_map, output_path)
        
        # FINALIZACIÓN
        job.status = "completed"
        job.current_step = "Synthesis complete. High-Fidelity Portfolio ready."
        job.progress = 100
        job.pptx_path = output_path
        job.download_url = f"/uploads/{output_filename}"
        db.commit()
        
    except Exception as e:
        import traceback
        print(f"  [Orchestrator v23.0] Critical Failure: {traceback.format_exc()}")
        job.status = "error"
        job.current_step = f"Synthesis interrupted: {str(e)}"
        db.commit()
