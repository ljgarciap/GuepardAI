import os
import json
import models
from sqlalchemy.orm import Session
from llm_provider import generate_json
from services.asset_library_service import find_best_assets
from typing import List, Dict
from services.font_service import ensure_brand_fonts

from services.asset_library_service import find_best_assets

def plan_presentation_design(db: Session, job_id: int):
    """
    PHASE 2: Art Direction (Planning).
    Iterates slide by slide to make aesthetic decisions.
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
    
    archetypes = ["split-right", "full-bleed", "two-column", "quote-hero", "data-grid", "asymmetric-overlay", "editorial-magazine", "dark-hero"]
    if essence and essence.slide_archetypes:
        archetypes = list(essence.slide_archetypes.keys())
    
    # v71.0: Dynamic Font Synchronization and Database Persistence
    if dna_record:
        dna_dict = dna_record.to_dict() if hasattr(dna_record, "to_dict") else vars(dna_record)
        ensure_brand_fonts(db, job.brand_id, dna_dict)

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
        
        # Mapeo a formato de planning con filtro Anti-Logo
        found_assets = []
        for a in asset_records:
            # CANDADO: Prohibir logos en slides internas para forzar fotos reales
            if slide.slide_number > 1 and a.category == "logos":
                continue
                
            found_assets.append({
                "id": a.id,
                "category": a.category, # Informar a la IA
                "path": a.local_path, 
                "description": a.description,
                "tags": a.tags
            })
        
        if not found_assets:
            # Fallback to simple search without logos or noise
            asset_records = db.query(models.BrandAsset).filter(models.BrandAsset.category.notin_(["logos", "noise"])).limit(5).all()
            found_assets = [{"id": a.id, "category": a.category, "path": a.local_path, "description": a.description} for a in asset_records]

        # B. Validación de Integridad de Marca (v33.5 - No Fallbacks)
        brand_record = db.query(models.Brand).get(job.brand_id)
        if not brand_record:
            raise ValueError(f"CRITICAL COHESION ERROR: Brand ID {job.brand_id} not found in database. Generation aborted to prevent inconsistency.")
        
        client_name = job.client_name or brand_record.name
        
        is_decoration = any(word in str(found_assets).lower() for word in ["fruit", "lime", "lemon", "isolated", "decoration", "object"])
        forced_layout_note = "DUE TO DECORATIVE ASSETS: Prefer 'marketing-hero'." if is_decoration else "Prefer 'split-right' or 'full-bleed'."

        # Preparar diccionarios para el prompt v55.0
        visual_dna_dict = {
            "primary_color": dna_record.primary_color if dna_record else "#0052A3",
            "secondary_color": dna_record.secondary_color if dna_record else "#FF142B",
            "primary_font": dna_record.primary_font if dna_record else "Arial"
        }
        
        # Evitar Repetición de Temas Visuales (v66.1)
        recent_assets = db.query(models.ArtDirectorDecision).filter(
            models.ArtDirectorDecision.job_id == job_id,
            models.ArtDirectorDecision.decision_type == "design_manifest"
        ).order_by(models.ArtDirectorDecision.slide_number.desc()).limit(5).all()
        used_descriptions = [d.reasoning for d in recent_assets]
        
        strategic_context = f"Strategic Context: {client_name} and its ecosystem."
        
        # El Rulebook dinámico extraído del ADN de la marca
        brand_rulebook = essence.art_direction_note if essence else "Standard corporate style: clean and professional."

        # Carga dinámica del Prompt desde la DB (v67.0)
        config_record = db.query(models.SystemConfig).filter(models.SystemConfig.key == "prompt_art_director_v1").first()
        if not config_record:
            raise Exception("CRITICAL: 'prompt_art_director_v1' not found in system_configs table.")
        
        prompt_template = config_record.value
        prompt = prompt_template.format(
            strategic_context=strategic_context,
            primary_color=visual_dna_dict["primary_color"],
            secondary_color=visual_dna_dict["secondary_color"],
            primary_font=visual_dna_dict["primary_font"],
            brand_rulebook=brand_rulebook,
            used_descriptions=json.dumps(used_descriptions),
            slide_title=slide.title,
            bullets=json.dumps(bullets),
            found_assets=json.dumps(found_assets)
        )
        
        print(f"    [ArtDirector] Planning Slide {slide.slide_number} for {client_name}...")
        decision = generate_json(prompt)
        
        # C. Generate Rendering Manifesto (v32.0 - Collision Protection)
        from services.brand_composition_dna import get_layout_geometry
        
        # 1. Obtener IDs de la Decisión (v67.5 - SAFE PARSING)
        def safe_int_id(val):
            if val is None: return None
            try: return int(val)
            except: return None

        primary_id = safe_int_id(decision.get("primary_asset_id"))
        accent_id = safe_int_id(decision.get("accent_id"))
        layout_slug = decision.get("layout_slug", "split-right")
        
        # VALIDACIÓN DE ARQUETIPO (v71.0)
        if layout_slug not in archetypes:
            layout_slug = "split-right"
        
        # STRATEGIC SHIELD
        # If the AI tries to use a decorative element as a giant background, we override it.
        if primary_id:
            primary_asset_record = db.query(models.BrandAsset).get(primary_id)
            if primary_asset_record and primary_asset_record.category == "design_elements":
                if not accent_id: accent_id = primary_id
                primary_id = None
                
        # If the AI is picky and decides "not to use image", WE FORCE IT.
        if not primary_id:
            fallback_photo = db.query(models.BrandAsset).filter(
                models.BrandAsset.category == "lifestyle_photos",
                models.BrandAsset.id.not_in(used_assets)
            ).order_by(models.BrandAsset.width.desc()).first()
            
            # ANTI-AMNESIA EXHAUSTION FIX (v23.0): Si se acabaron las únicas, reciclar.
            if not fallback_photo:
                from sqlalchemy.sql.expression import func
                fallback_photo = db.query(models.BrandAsset).filter(
                    models.BrandAsset.category == "lifestyle_photos"
                ).order_by(func.random()).first()
                
            primary_id = fallback_photo.id if fallback_photo else None

        # GUARDAR MEMORIA
        if primary_id: used_assets.append(primary_id)
        if accent_id: used_assets.append(accent_id)

        # 2. Calcular Geometría Protegida
        title_len = len(slide.title)
        estimated_lines = max(1, title_len // 35 + 1)
        geo = get_layout_geometry(layout_slug, 13.33, 7.5, title_lines=estimated_lines)
        
        render_elements = []

        # 2.5 Inyectar Logo de Marca (Obligatorio, Esquina Superior Derecha para evitar choques)
        if logo_asset:
            render_elements.append({
                "type": "logo", "role": "logo",
                "path": logo_asset.local_path,
                "geometry": {"top": 4.0, "left": 86.0, "width": 10.0, "height": 10.0} 
            })

        # 3. Construir Título
        title_f_size = 36 if title_len > 60 else 42
        render_elements.append({
            "type": "text", "role": "title", "content": slide.title,
            "geometry": geo["title"],
            "style": {
                "size": title_f_size, "bold": True, 
                "color": dna_record.primary_color if dna_record else "#0052A3",
                "font": dna_record.primary_font if dna_record else "Helvetica Neue"
            }
        })

        # 4. Construir Cuerpo
        # Verificar si hay tabla para ajustar el layout
        table_decision = decision.get("table")
        has_table = table_decision and table_decision.get("data")
        
        # Ajuste de geometría si comparten espacio
        body_geo = geo["content"].copy()
        table_geo = geo.get("table", {"top": 50.0, "left": 7.0, "width": 86.0, "height": 35.0}).copy()
        
        if has_table:
            # Como solo dejaremos la primera viñeta, la caja de texto no necesita ser enorme
            body_geo["height"] = 12.0 # Suficiente para 2-3 líneas
            table_geo["top"] = body_geo["top"] + body_geo["height"] + 2.0
            table_geo["left"] = body_geo["left"]
            table_geo["width"] = body_geo["width"]
            
            # Dinamismo de tabla (4 filas = ~30 height, 6 filas = ~40 height)
            table_rows = len(table_decision["data"])
            table_geo["height"] = min(50.0, max(25.0, table_rows * 6.0))

        # 4. Construir Texto de Cuerpo
        if has_table and len(bullets) > 0:
            bullet_text = f"• {bullets[0]}"
        else:
            bullet_text = "\n".join([f"• {b}" for b in bullets])
            
        # TIPOGRAFÍA DINÁMICA (v23.0)
        text_len = len(bullet_text)
        body_f_size = 18 if has_table else 24
        if not has_table:
            if text_len > 350: body_f_size = 18
            if text_len > 600: body_f_size = 14
            
        render_elements.append({
            "type": "text", "role": "body", "content": bullet_text,
            "geometry": body_geo,
            "style": {
                "size": body_f_size,
                "color": "#333333",
                "font": dna_record.primary_font if dna_record else "Helvetica Neue"
            }
        })

        # 5. Imagen Principal (Lifestyle/Contenido)
        if primary_id:
            asset = db.query(models.BrandAsset).get(primary_id)
            if asset:
                render_elements.append({
                    "type": "image", "role": "main",
                    "path": asset.local_path,
                    # Si geo["image"] es None (como en two-column), usar 'content' u otro fallback.
                    "geometry": geo.get("image") or geo.get("content", {"top": 0, "left": 50, "width": 50, "height": 100})
                })

        # 6. Acento de Diseño (Kiwi/DNA)
        if accent_id:
            accent_asset = db.query(models.BrandAsset).get(accent_id)
            if accent_asset:
                render_elements.append({
                    "type": "image", "role": "accent",
                    "path": accent_asset.local_path,
                    "geometry": geo.get("accent", {"top": 5.0, "left": 85.0, "width": 8.0, "height": 8.0})
                })

        # 7. Tabla de Datos (Si aplica)
        if has_table:
            render_elements.append({
                "type": "table", "role": "metrics",
                "data": table_decision["data"],
                "geometry": table_geo
            })

        # 8. Barra de Marca (Acento sutil v60.0)
        if dna_record and dna_record.secondary_color:
            render_elements.append({
                "type": "shape", "role": "brand_bar",
                "geometry": {"top": 16.0, "left": 7.0, "width": 30.0, "height": 0.4},
                "style": {"color": dna_record.secondary_color, "opacity": 1.0}
            })
            
        # 9. Fondo Especial (v71.0 - Layouts Premium)
        bg_shape_geo = geo.get("background_shape")
        if bg_shape_geo:
            render_elements.insert(0, { # Insertar al principio para que esté detrás
                "type": "shape", "role": "background_box",
                "geometry": bg_shape_geo,
                "style": {
                    "color": dna_record.primary_color if dna_record else "#0052A3",
                    "opacity": 0.15 # Sutil traslúcido
                }
            })

        # 8. Guardar Decisión y Bitácora
        new_decision = models.ArtDirectorDecision(
            job_id=job_id,
            slide_number=slide.slide_number,
            decision_type="design_manifest",
            summary=f"Layout: {layout_slug} | Primary: {primary_id} | Accent: {accent_id}",
            reasoning=json.dumps(decision.get("reasoning")) if isinstance(decision.get("reasoning"), dict) else decision.get("reasoning", "Aesthetic alignment."),
            metadata_json={
                "layout_slug": layout_slug,
                "primary_asset_id": primary_id,
                "accent_id": accent_id,
                "render_elements": render_elements
            }
        )
        db.add(new_decision)
        
        # 9. ACTUALIZAR LA SLIDE REAL (v67.2 - CRITICAL FIX)
        slide.layout_slug = layout_slug
        slide.render_elements = render_elements
        slide.status = "planned"
        
        db.commit()
        
    return True
