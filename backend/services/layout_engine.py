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

def apply_design_policy(content_manifest: dict, brand_dna, brand_essence=None, job_id=None, db=None) -> dict:
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
    model_name = get_system_config("art_director_model", "gpt-4o-mini")

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
        from llm_provider import generate_premium_json
        planning = generate_premium_json(art_director_prompt)
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
            title=slide.get("title") or "Untitled",
            content_json=slide,
            layout_slug=layout,
            assigned_image=slide.get("assigned_image"),
            reference_id=plan.get("reference_id"),
            font_scale=plan.get("font_scale", 1.0),
            render_elements=elements,
            planning_json={
                "layout_reasoning": f"Chose {layout} based on {stype} strategy",
                "grammar_logic": elements.get("grammar_type", "standard") if isinstance(elements, dict) else "standard"
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
    ORQUESTADOR MAESTRO V11 (Decoupled Architecture).
    Coordina: Content -> Art Director (Base/Premium) -> RenderManifest -> GammaPainter
    """
    from services.content_service import synthesize_presentation_outline
    from services.decoupled_art_director import BaseArtDirector, PremiumArtDirector
    from services.painter import GammaPainter
    from schemas.presentation import RenderManifest, PainterSlideData, PainterAgencyBranding
    from painter_bridge import GRAMMAR_TO_PAINTER

    job = db.query(models.GenerationJob).get(job_id)
    if not job: return

    try:
        # FASE 1: SÍNTESIS DE CONTENIDO
        job.status = "processing"
        job.current_step = "Phase 1/3: Synthesizing strategic content..."
        job.progress = 10
        db.commit()
        
        if req_data.get("skip_content"):
            print("  [Flow] Skipping content synthesis, building manifest from DB...")
            from schemas.presentation import ContentManifest, ContentManifestSlide
            slides = []
            saved_slides = db.query(models.PresentationSlide).filter(models.PresentationSlide.job_id == job_id).order_by(models.PresentationSlide.slide_number.asc()).all()
            for s in saved_slides:
                cjson = s.content_json or {}
                slides.append(ContentManifestSlide(
                    slide_number=s.slide_number,
                    title=s.title,
                    subtitle=cjson.get("subtitle"),
                    bullets=cjson.get("bullets", []),
                    metrics=cjson.get("metrics", []),
                    metric=cjson.get("metric"),
                    label=cjson.get("label"),
                    layout_type=cjson.get("layout_type", "strategic_split"),
                    section_label=cjson.get("section_label"),
                    metadata=cjson.get("metadata", {}),
                    planning_json=s.planning_json or {}
                ))
            content_manifest = ContentManifest(job_id=job_id, slides=slides)
        else:
            content_manifest = synthesize_presentation_outline(db, job_id, req_data)
            
        if not content_manifest:
            raise Exception("Failed during Content Synthesis.")

        # FASE 2: DIRECCIÓN DE ARTE
        tier = req_data.get("tier", "free")
        is_premium = (tier == "premium")
        
        job.current_step = f"Phase 2/3: Art Direction ({'Premium SVG' if is_premium else 'Base Asset'} Mode)..."
        job.progress = 40
        db.commit()
        
        # Obtener el Brand DNA
        dna = db.query(models.BrandVisualDna).filter(models.BrandVisualDna.brand_id == job.brand_id).order_by(models.BrandVisualDna.created_at.desc()).first()
        design_system = {
            "primary_color": getattr(dna, "primary_color", "#0052A3"),
            "secondary_color": getattr(dna, "secondary_color", "#EE1C2E"),
            "background_color": getattr(dna, "background_color", "#FFFFFF"),
        }
        
        uploads_dir = os.path.abspath("uploads")
        if not os.path.exists(uploads_dir):
            uploads_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))

        art_director = PremiumArtDirector(db, job_id, uploads_dir) if is_premium else BaseArtDirector(db, job_id)
        
        base_design = art_director.plan(content_manifest)
        if is_premium:
            final_design = art_director.enrich_design(base_design, content_manifest, design_system)
        else:
            # Here we would normally extract assets from DB for Base mode, but skipping for brevity
            final_design = base_design

        job.current_step = "Phase 3/3: Assembling native decoupled presentation..."
        job.progress = 80
        db.commit()

        # FASE 3: ENSAMBLAJE (RENDER MANIFEST & PAINTER)
        output_format = req_data.get("output_format", "pptx")
        
        if output_format == "pdf_artistic":
            raise NotImplementedError("PDF Artistic not migrated to V11 decoupled flow yet.")
            
        # Construir RenderManifest
        agency_name_cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == "agency_name").first()
        agency_name = agency_name_cfg.value if agency_name_cfg else "L-Founders"
        
        # Buscar el logo oficial de la marca
        brand_logo = db.query(models.BrandAsset).filter(
            models.BrandAsset.brand_id == job.brand_id,
            models.BrandAsset.category == "logos"
        ).first()
        brand_logo_path = os.path.basename(brand_logo.local_path) if brand_logo else None
        
        agency_branding = PainterAgencyBranding(
            name=agency_name,
            logo_path=brand_logo_path,
            client_name="Client",
            email="partners@l-founders.com"
        )
        
        render_slides = []
        for i, c_slide in enumerate(content_manifest.slides):
            d_slide = final_design.slides[i]
            
            p_layout = GRAMMAR_TO_PAINTER.get(c_slide.layout_type, "composition_split")
            
            render_slides.append(PainterSlideData(
                slide_number=c_slide.slide_number,
                layout_type=p_layout,
                title=c_slide.title,
                bullets=c_slide.bullets,
                metrics=c_slide.metrics,
                metric=c_slide.metric,
                label=c_slide.label,
                tag=c_slide.section_label or "STRATEGY",
                primary_asset_path=d_slide.primary_asset_path,
                background_asset_path=d_slide.background_asset_path,
                is_last=(i == len(content_manifest.slides) - 1),
                logo_path=brand_logo_path,
                agency_branding=agency_branding,
                metadata=c_slide.metadata,
                elements=[]
            ))
            
        render_manifest = RenderManifest(
            slides=render_slides,
            logo_path=brand_logo_path,
            agency_branding=agency_branding
        )
        
        output_filename = f"Portfolio_V11_{'Premium' if is_premium else 'Free'}_{job_id}_{int(time.time())}.pptx"
        output_path = os.path.join(uploads_dir, output_filename)
        
        painter = GammaPainter(dna)
        painter.render_slides(render_manifest)
        painter.save(output_path)
        
        download_url = f"/uploads/{output_filename}"
        job.pptx_path = output_path
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
