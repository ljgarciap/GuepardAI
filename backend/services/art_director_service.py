import os
import json
import models
from sqlalchemy.orm import Session
from llm_provider import generate_json
from services.asset_library_service import find_best_assets
from typing import List, Dict

from services.asset_library_service import find_best_assets

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
        
        # A. Búsqueda Semántica Vectorial (v28.0 - RAG REAL)
        bullets = slide.content_json.get("bullets", [])
        content_keywords = [slide.title]
        if bullets:
            all_text = " ".join(bullets).lower()
            important_words = [w for w in all_text.split() if len(w) > 4 and w not in ["this", "that", "with", "from"]]
            content_keywords.extend(important_words[:5]) 
        
        # Búsqueda matemática por vectores
        asset_records = find_best_assets(
            db, 
            job.brand_id, 
            content_keywords, 
            limit=10, 
            exclude_ids=used_assets if used_assets else None
        )
        
        # Mapeo a formato de planning
        found_assets = []
        for a in asset_records:
            found_assets.append({
                "id": a.id, # Usamos ID real para mayor precisión
                "filename": os.path.basename(a.local_path),
                "path": a.local_path, 
                "description": a.description,
                "tags": a.tags
            })
        
        if not found_assets:
            # Fallback a búsqueda simple si no hay nada semántico
            asset_records = db.query(models.BrandAsset).limit(3).all()
            found_assets = [{"id": os.path.basename(a.local_path), "path": a.local_path, "description": a.description} for a in asset_records]

        # B. Validación de Integridad de Marca (v33.5 - No Fallbacks)
        brand_record = db.query(models.Brand).get(job.brand_id)
        if not brand_record:
            raise ValueError(f"CRITICAL COHESION ERROR: Brand ID {job.brand_id} not found in database. Generation aborted to prevent inconsistency.")
        
        client_name = job.client_name or brand_record.name
        
        is_decoration = any(word in str(found_assets).lower() for word in ["fruit", "lime", "lemon", "isolated", "decoration", "object"])
        forced_layout_note = "DUE TO DECORATIVE ASSETS: Prefer 'marketing-hero'." if is_decoration else "Prefer 'split-right' or 'full-bleed'."

        prompt = f"""
        ### ROLE: SENIOR BRAND ART DIRECTOR
        Strategic Context: {client_name} and its ecosystem.
        
        GROUNDING RULES:
        1. CONTEXTUAL BRANDING: You may use assets of partners, allies, or case studies ONLY IF they appear in the provided context.
        2. NO OVERLAP: Maintain strict geometry margins.
        BRAND DNA (STRICT ADHERENCE):
        - Primary Color: {visual_dna_dict['primary_color']}
        - Secondary Color: {visual_dna_dict['secondary_color']}
        - Main Font: {visual_dna_dict['primary_font']}
    
        ARTISTIC DIRECTION NOTE (MANDATORY):
        {artistic_essence_dict['visual_strategy']}
    
        STRICT ASSET RULES:
        1. PARTNER/COMPETITOR LOGOS (e.g. Carrefour, Loblaw): Use them ONLY for comparative slides or case studies mentioned in the text. 
        2. BRAND REPRESENTATION: If the slide is about "Our Company" or "{brand_record.name}", use ONLY {brand_record.name} assets.
        3. NO DECORATIVE METAPHORS: Do not use avocados, gears, or puzzles unless explicitly requested.
        
        Slide Title: {slide.title}
        Content: {json.dumps(bullets)}
        
        AVAILABLE ASSETS:
        {json.dumps(found_assets)}
        
        INSTRUCTION: Pick EXACTLY ONE layout_slug from: ["marketing-hero", "split-right", "full-bleed", "two-column"].
        {forced_layout_note}
        
        Return ONLY JSON:
        {{ 
          "layout_slug": "ONE_OF_THE_SLUGS_ABOVE", 
          "assigned_image_id": "ID_FROM_AVAILABLE_ASSETS", 
          "reasoning": "Strategy-driven explanation."
        }}
        """
        
        print(f"    [ArtDirector] Planning Slide {slide.slide_number} for {client_name}...")
        decision = generate_json(prompt)
        
        # C. Generar Manifiesto de Renderizado (v32.0 - Collision Protection)
        from services.brand_composition_dna import get_layout_geometry
        
        # 3. Imagen Principal (FILTRO ANTI-COMPETENCIA v50.0)
        target_id = decision.get("assigned_image_id")
        asset = db.query(models.BrandAsset).get(target_id) if target_id else None
        
        # Si el asset encontrado menciona a un competidor conocido, lo anulamos
        competitors = ["carrefour", "loblaw", "walmart", "lidl", "aldi", "sainsbury", "asda", "flybuys"]
        if asset and any(comp in (asset.description or "").lower() or comp in str(asset.tags).lower() for comp in competitors):
            # Solo bloqueamos si el competidor no es la marca actual
            if brand_record and all(comp not in brand_record.name.lower() for comp in competitors):
                print(f"    [ArtDirector] ALERT: Competitor asset '{asset.description}' blocked for {brand_record.name}")
                asset = None
                target_id = None

        layout_slug = decision.get("layout_slug", "split-right")
        
        # Calcular Geometría Dinámica
        geo = get_layout_geometry(layout_slug, 13.33, 7.5, title_lines=max(1, len(slide.title) // 45 + 1))
        
        render_elements = []
        
        # 1. Título
        render_elements.append({
            "type": "text", "role": "title", "content": slide.title,
            "geometry": geo["title"],
            "style": {
                "size": 42, 
                "bold": True, 
                "color": dna_record.primary_color if dna_record else "#0052A3",
                "font": dna_record.primary_font if dna_record else "Arial"
            }
        })
        
        # 2. Cuerpo (Bullets)
        bullet_text = "\n".join([f"• {b}" for b in bullets])
        render_elements.append({
            "type": "text", "role": "body", "content": bullet_text,
            "geometry": geo["content"],
            "style": {
                "size": 24, 
                "color": dna_record.text_main_color if dna_record else "#111111",
                "font": dna_record.primary_font if dna_record else "Arial"
            }
        })

        # 2.5 Acento de Marca (Barra distintiva v51.0)
        if dna_record and dna_record.secondary_color:
            render_elements.append({
                "type": "shape", "role": "brand_bar",
                "geometry": {"top": 15.0, "left": 7.0, "width": 5.0, "height": 0.5},
                "style": {"color": dna_record.secondary_color, "opacity": 1.0}
            })
        
        # 3. Imagen Principal
        if geo["image"] and asset:
            render_elements.append({
                "type": "image", "role": "hero", "source": os.path.basename(asset.local_path),
                "geometry": geo["image"],
                "width": asset.width,
                "height": asset.height
            })
            
        # 4. Logo de Marca (Esquina Superior Derecha - PORCENTAJES v50.0)
        if logo_id:
            render_elements.append({
                "type": "logo", "role": "brand_logo", "source": logo_id,
                "geometry": {"top": 3.0, "left": 85.0, "width": 12.0, "height": 8.0}
            })

        # Persistencia Total
        slide.layout_slug = layout_slug
        slide.assigned_image = os.path.basename(asset.local_path) if asset else None
        slide.render_elements = render_elements
        
        if target_id: used_assets.append(target_id)
        
        slide.status = "planned"
        
        # D. Registrar Bitácora de Decisión (v34.0 - Transparency)
        log_entry = models.ArtDirectorDecision(
            job_id=job_id,
            slide_number=slide.slide_number,
            decision_type="visual_planning",
            summary=f"Layout: {layout_slug} | Asset: {slide.assigned_image}",
            reasoning=decision.get("reasoning", "No explicit reasoning provided."),
            metadata_json={
                "layout_slug": layout_slug,
                "assigned_asset_id": target_id,
                "keywords_used": content_keywords,
                "assets_found_count": len(found_assets)
            }
        )
        db.add(log_entry)
        db.commit()
        
    return True
