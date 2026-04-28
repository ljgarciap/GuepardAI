import os
import json
import models
from sqlalchemy.orm import Session
from llm_provider import generate_json
from services.asset_library_service import find_best_assets
from typing import List, Dict

def find_best_assets_tiered(db: Session, brand_id: int, style_filename: str, keywords: List[str], category: str = "photos", limit: int = 5, exclude_ids: List[str] = None) -> List[dict]:
    """
    BÚSQUEDA JERÁRQUICA DE ACTIVOS (v23.0).
    Prioridad: 1. Style (Blueprint) | 2. Brand | 3. Public
    """
    all_results = []
    if not exclude_ids: exclude_ids = []
    
    # 1. Búsqueda en el STYLE (Blueprint) específico
    print(f"    [ArtDirector] Priority 1: Searching in Style '{style_filename}'...")
    from sqlalchemy import or_
    style_query = db.query(models.BrandAsset).filter(
        models.BrandAsset.source_doc == style_filename,
        models.BrandAsset.category == category
    )
    for exc in exclude_ids:
        style_query = style_query.filter(~models.BrandAsset.local_path.contains(exc))
        
    style_assets = style_query.limit(limit).all()
    
    for a in style_assets:
        all_results.append({"id": os.path.basename(a.local_path), "path": a.local_path, "source": "style", "description": a.description})

    # 2. Si no hay suficientes, buscar en la MARCA
    if len(all_results) < limit:
        print(f"    [ArtDirector] Priority 2: Searching in Brand ID {brand_id}...")
        brand_query = db.query(models.BrandAsset).filter(
            models.BrandAsset.brand_id == brand_id,
            models.BrandAsset.source_doc != style_filename, 
            models.BrandAsset.category == category
        )
        for exc in exclude_ids:
            brand_query = brand_query.filter(~models.BrandAsset.local_path.contains(exc))
            
        brand_assets = brand_query.limit(limit - len(all_results)).all()
        for a in brand_assets:
            all_results.append({"id": os.path.basename(a.local_path), "path": a.local_path, "source": "brand", "description": a.description})

    # 3. Si sigue faltando, buscar en la LIBRERÍA PÚBLICA
    if len(all_results) < limit:
        print(f"    [ArtDirector] Priority 3: Searching in Global Library...")
        public_query = db.query(models.BrandAsset).filter(
            models.BrandAsset.is_public == 1,
            models.BrandAsset.category == category
        )
        for exc in exclude_ids:
            public_query = public_query.filter(~models.BrandAsset.local_path.contains(exc))
            
        public_assets = public_query.limit(limit - len(all_results)).all()
        for a in public_assets:
            all_results.append({"id": os.path.basename(a.local_path), "path": a.local_path, "source": "public", "description": a.description})

    return all_results

def plan_presentation_design(db: Session, job_id: int):
    """
    FASE 2: Dirección de Arte (Planificación).
    Itera slide por slide para tomar decisiones estéticas.
    """
    job = db.query(models.GenerationJob).get(job_id)
    if not job: return False
    
    slides = db.query(models.PresentationSlide).filter(
        models.PresentationSlide.job_id == job_id,
        models.PresentationSlide.status == "content_ready"
    ).order_by(models.PresentationSlide.slide_number.asc()).all()
    
    if not slides:
        print("  [ArtDirector] No slides ready for planning.")
        return False

    # Obtener Blueprint / Style para la jerarquía v23.0
    style_filename = ""
    if job.style_id:
        dna_record = db.query(models.BrandVisualDna).get(job.style_id)
        if dna_record:
            style_filename = dna_record.source_filename
    
    print(f"  [ArtDirector] Planning design for {len(slides)} slides using style '{style_filename}'...")
    
    # 1. Obtener Esencia Artística para los arquetipos disponibles
    essence = db.query(models.BrandArtisticEssence).filter(
        models.BrandArtisticEssence.brand_id == job.brand_id
    ).order_by(models.BrandArtisticEssence.created_at.desc()).first()
    
    archetypes = ["split-right", "full-bleed", "two-column", "quote-hero", "data-grid"]
    if essence and essence.slide_archetypes:
        archetypes = list(essence.slide_archetypes.keys())

    # 1. Buscar el LOGO real de la marca v23.5
    logo_asset = db.query(models.BrandAsset).filter(
        models.BrandAsset.brand_id == job.brand_id,
        models.BrandAsset.category == "logos"
    ).first()
    logo_id = os.path.basename(logo_asset.local_path) if logo_asset else None

    # Lista de exclusión para evitar repeticiones excesivas
    used_assets = []
    
    for slide in slides:
        print(f"    [ArtDirector] Planning Slide {slide.slide_number}: '{slide.title}'")
        
        # A. Búsqueda Jerárquica de Imágenes
        intent = slide.content_json.get("visual_intent")
        keywords = [intent] if intent else [slide.title]
        
        found_assets = find_best_assets_tiered(
            db, 
            job.brand_id, 
            style_filename, 
            keywords, 
            exclude_ids=[a for a in used_assets if used_assets.count(a) >= 2]
        )
        
        # Fallback de Seguridad: Si no hay nada, cargar lo más relevante del Style sin exclusión
        if not found_assets:
            found_assets = find_best_assets_tiered(db, job.brand_id, style_filename, [slide.title], limit=3)

        # B. Consulta al Art Director LLM
        prompt = f"""
        ### ROLE: ELITE ART DIRECTOR
        Slide: {slide.title}
        Bullets: {json.dumps(slide.content_json.get("bullets"))}
        
        AVAILABLE ASSETS (Priority order):
        {json.dumps(found_assets)}
        
        RULES:
        1. If bullets exist, you MUST use a content-rich layout ('split-right', 'two-column').
        2. Avoid 'full-bleed' unless it's a section transition.
        3. You MUST assign an 'assigned_image' from the list. Do not leave it empty.
        
        Return ONLY JSON:
        {{ "layout_slug": "...", "assigned_image": "...", "reasoning": "..." }}
        """
        
        decision = generate_json(prompt)
        assigned = decision.get("assigned_image")
        
        # C. Persistir y forzar Logo
        slide.layout_slug = decision.get("layout_slug", "split-right")
        slide.assigned_image = assigned if assigned else (found_assets[0]["id"] if found_assets else None)
        if assigned: used_assets.append(assigned)
        
        slide.planning_json = {
            "reasoning": decision.get("reasoning"),
            "assets_considered": found_assets,
            "logo_id": logo_id # Inyectamos el logo real detectado
        }
        slide.status = "planned"
        db.commit()
        
    return True
