import models
from sqlalchemy.orm import Session
from services.brand_composition_dna import parse_essence_to_policy, build_slide_elements

def calculate_presentation_geometry(db: Session, job_id: int):
    """
    FASE 3: Cálculo Geométrico (Determinismo).
    Convierte planes abstractos en coordenadas reales.
    """
    job = db.query(models.GenerationJob).get(job_id)
    if not job: return False
    
    slides = db.query(models.PresentationSlide).filter(
        models.PresentationSlide.job_id == job_id,
        models.PresentationSlide.status == "planned"
    ).order_by(models.PresentationSlide.slide_number.asc()).all()
    
    if not slides:
        print("  [GeometryService] No slides planned for geometry.")
        return False
        
    # 1. Preparar Política de Marca (Global para el Job)
    dna = db.query(models.BrandVisualDna).filter(
        models.BrandVisualDna.brand_id == job.brand_id
    ).order_by(models.BrandVisualDna.created_at.desc()).first()
    
    essence = db.query(models.BrandArtisticEssence).filter(
        models.BrandArtisticEssence.brand_id == job.brand_id
    ).order_by(models.BrandArtisticEssence.created_at.desc()).first()
    
    if not dna or not essence:
        print("  [GeometryService] Missing Brand DNA or Essence.")
        return False
        
    # Consolidar esencia artística desde sus columnas v23.1
    essence_dict = {
        "slide_archetypes": essence.slide_archetypes or {},
        "structural_archetypes": essence.structural_archetypes or {},
        "design_gestures": essence.design_gestures or {},
        "composition_rules": essence.composition_rules or {},
        "art_direction_note": essence.art_direction_note
    }
    
    policy = parse_essence_to_policy(
        brand_id=job.brand_id,
        brand_name=job.client_name,
        artistic_essence=essence_dict,
        visual_dna=dna.raw_extraction or {},
        force_width=dna.slide_width_inches,
        force_height=dna.slide_height_inches
    )
    
    print(f"  [GeometryService] Calculating geometry for {len(slides)} slides...")
    
    for slide in slides:
        print(f"    [GeometryService] Mapping Slide {slide.slide_number} to canvas...")
        
        # 2. Construcción de Elementos Geométricos
        # Reutilizamos build_slide_elements pero adaptado a la nueva DB
        # Simulamos los diccionarios que espera build_slide_elements
        slide_dict = {
            "title": slide.title,
            "bullets": slide.content_json.get("bullets", []),
            "assigned_image": slide.assigned_image,
            "slide_number": slide.slide_number,
            "planning_json": slide.planning_json # Inyectamos planning para el Logo
        }
        
        visual_dna_dict = dna.raw_extraction or {}
        
        elements, layout_used = build_slide_elements(
            slide=slide_dict,
            slide_type=slide.layout_slug,
            slide_index=slide.slide_number,
            total_slides=len(slides),
            policy=policy,
            visual_dna=visual_dna_dict,
            full_bleed_budget={}, # Por ahora
            font_scale_override=slide.font_scale or 1.0
        )
        
        # 3. Persistir Elementos Finales
        slide.render_elements = elements
        slide.status = "rendered"
        db.commit()
        
    return True
