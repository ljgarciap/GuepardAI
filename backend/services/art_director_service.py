import os
import json
import models
import time
from sqlalchemy.orm import Session
from llm_provider import generate_json, generate_ai_image
from services.asset_library_service import find_best_assets
from services.analyst_service import get_slide_visual_strategy
from services.placeholder_service import get_placeholder_image
from services.brand_composition_dna import get_layout_geometry, build_decorator_elements
from services.font_service import ensure_brand_fonts

def plan_presentation_design(db: Session, job_id: int):
    """
    STRATEGIC DESIGN ENGINE v4.0.
    Sequential flow: Analysis -> Asset Scoring -> Audited Execution.
    """
    job = db.query(models.GenerationJob).get(job_id)
    if not job: return False
    
    # 0. Cargar Configuraciones Paramétricas (v4.0)
    threshold_cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == "asset_score_threshold").first()
    THRESHOLD = float(threshold_cfg.value) if threshold_cfg else 0.70
    
    slides = db.query(models.PresentationSlide).filter(
        models.PresentationSlide.job_id == job_id,
        models.PresentationSlide.status == "content_ready"
    ).order_by(models.PresentationSlide.slide_number.asc()).all()
    
    if not slides:
        print("  [ArtDirector] No slides ready for planning.")
        return False

    dna_record = db.query(models.BrandVisualDna).filter(models.BrandVisualDna.brand_id == job.brand_id).first()
    p_color = dna_record.primary_color if dna_record else "#0052A3"
    s_color = dna_record.secondary_color if dna_record else "#EE1C2E"
    
    # 1. Obtener Logo de Marca (Prioridad: Perfil de Marca -> Librería)
    brand_rec = db.query(models.Brand).get(job.brand_id)
    logo_path = None
    if brand_rec and brand_rec.logo_path:
        logo_path = brand_rec.logo_path
    else:
        logo_asset = db.query(models.BrandAsset).filter(
            models.BrandAsset.brand_id == job.brand_id,
            models.BrandAsset.category == "logos"
        ).first()
        if logo_asset:
            logo_path = logo_asset.local_path

    prompt_tpl = db.query(models.SystemConfig).filter(models.SystemConfig.key == "prompt_art_director_v1").first()

    used_assets = []
    
    for slide in slides:
        print(f"    [Engine v4.0] Strategic Planning for Slide {slide.slide_number}...")
        
        # FASE A: ANALISTA ESTRATÉGICO
        strategy = get_slide_visual_strategy(db, slide, job)
        visual_intent = strategy.get("visual_intent", "Executive")

        # v8.0: El Analista decide el grammar_type — el Art Director lo respeta
        analyst_grammar_type = strategy.get("grammar_type", "composition_split")

        # Enriquecer content_json del slide con lo que detectó el Analista (v8.0)
        if strategy.get("metric_value") and not slide.content_json.get("metric"):
            content = dict(slide.content_json or {})
            content["metric"] = strategy["metric_value"]
            slide.content_json = content
            db.commit()
        
        # FASE B: BÚSQUEDA EN CASCADA (Protocolo v6.0)
        from services.asset_library_service import find_assets_by_tags
        
        search_keywords = slide.content_json.get("visual_tags", [])
        if not search_keywords:
            search_keywords = strategy.get("suggested_keywords", [slide.title])
        
        print(f"    [ArtDirector] Protocol v6.0 Sequence for Slide {slide.slide_number}:")
        
        # NIVEL 1: Definición Semántica (Embedding)
        asset_candidates = find_best_assets(db, job.brand_id, search_keywords, limit=12, exclude_ids=used_assets)
        best_semantic = max([s for a, s in asset_candidates] + [0])
        
        if best_semantic >= 0.60:
            print(f"      - Level 1 Success: Semantic match found ({best_semantic:.2f})")
        else:
            print(f"      - Level 1 Weak ({best_semantic:.2f}). Trying Level 2 (3-Tag Intersection)...")
            # NIVEL 2: Intersección 3 Tags
            asset_candidates = find_assets_by_tags(db, job.brand_id, search_keywords, min_matches=3, limit=12, exclude_ids=used_assets)
            
            if asset_candidates:
                print(f"      - Level 2 Success: 3-tag match found")
            else:
                print(f"      - Level 2 Failed. Trying Level 3 (2-Tag Intersection)...")
                # NIVEL 3: Intersección 2 Tags
                asset_candidates = find_assets_by_tags(db, job.brand_id, search_keywords, min_matches=2, limit=12, exclude_ids=used_assets)
            if asset_candidates:
                print(f"      - Level 3 Success: 2-tag match found")
            else:
                print(f"      - All Library Levels Failed for Slide {slide.slide_number}")
                
                # FASE B.X: GENERACIÓN BAJO DEMANDA (v7.0 "The Creator")
                if job.allow_ai_images:
                    print(f"    [ArtDirector] ACTION: Library empty. Triggering Gemini Creator...")
                    from llm_provider import generate_ai_image
                    from services.asset_library_service import register_asset
                    
                    gen_path = generate_ai_image(visual_intent)
                    if gen_path:
                        new_asset = register_asset(db, job.brand_id, gen_path, category="lifestyle_photos")
                        if new_asset:
                            asset_candidates = [(new_asset, 0.99)]
                            print(f"      - Level AI Success: Created and registered Asset {new_asset.id}")
                else:
                    print(f"    [ArtDirector] ACTION: AI Disabled. Falling back to placeholder.")

        # Filtrar assets por umbral y resolución (v8.5)
        filtered_assets = []
        audit_metadata = {"considered": [], "rejected": []}
        
        # Obtener el layout sugerido por el analista para el filtro de resolución
        suggested_layout = strategy.get("grammar_type", "strategic_split")
        requires_hi_res = suggested_layout in ["hero", "full_brand_overlay", "big_image"]
        
        for asset, score in asset_candidates:
            asset_info = {"id": asset.id, "score": score, "category": asset.category, "desc": asset.description[:50]}
            
            # REGLA DE CALIDAD v8.9: Verificación Física si no hay Metadata
            res_ok = True
            min_required = 1024 if requires_hi_res else 400
            
            w, h = asset.width, asset.height
            if not w and asset.local_path and os.path.exists(asset.local_path):
                try:
                    with Image.open(asset.local_path) as img:
                        w, h = img.size
                except: pass

            if score >= 0.40 and res_ok: 
                filtered_assets.append(asset_info)
                audit_metadata["considered"].append(asset_info)
            else:
                audit_metadata["rejected"].append(asset_info)

        # FASE C: DIRECCIÓN DE ARTE (Ejecución con Memoria Visual)
        visual_history = []
        for uid in used_assets:
            u_asset = db.query(models.BrandAsset).get(uid)
            if u_asset: visual_history.append(u_asset.description[:100])

        prompt = prompt_tpl.value.format(
            visual_strategy=json.dumps(strategy),
            primary_color=p_color,
            secondary_color=s_color,
            primary_font=dna_record.primary_font if dna_record else "Arial",
            slide_title=slide.title,
            bullets=str(slide.content_json.get("bullets", [])),
            found_assets=json.dumps(filtered_assets),
            visual_history=json.dumps(visual_history)
        )
        
        decision = generate_json(prompt)
        
        # Robustness check
        if isinstance(decision, list) and len(decision) > 0: decision = decision[0]
        
        # FASE D: AUDITORÍA (Bitácora)
        raw_reasoning = decision.get("reasoning", "Strategic choice.")
        if isinstance(raw_reasoning, dict): raw_reasoning = json.dumps(raw_reasoning)

        audit = models.ArtDirectorDecision(
            job_id=job_id, slide_number=slide.slide_number, decision_type="layout_selection",
            summary=f"Intent: {visual_intent}", reasoning=raw_reasoning,
            prompt_used=prompt, response_raw=json.dumps(decision),
            metadata_json=audit_metadata
        )
        db.add(audit)

        # FASE E: ENSAMBLAJE DEL MANIFIESTO
        # v8.0: grammar_type viene del Analista, no del Art Director LLM
        grammar_type = analyst_grammar_type
        if isinstance(grammar_type, list) and len(grammar_type) > 0:
            grammar_type = grammar_type[0]
        grammar_type = str(grammar_type)
        
        primary_id = decision.get("primary_asset_id")
        accent_id = decision.get("accent_asset_id")
        
        # GUARDIA DE HIERRO (v8.5) - Prioridad Library y No Repetición
        valid_ids = [a["id"] for a in filtered_assets]
        
        if (not primary_id or primary_id not in valid_ids) and filtered_assets:
            print(f"    [ArtDirector] FORCING: LLM rejected/missed candidates. Using best library match: {filtered_assets[0]['id']}")
            primary_id = filtered_assets[0]["id"]
        
        # FASE E.2: THE CREATOR (v8.5) - Solo si de verdad NO hay nada en la librería de calidad
        if not primary_id and job.allow_ai_images:
            print(f"    [ArtDirector] ACTION: Quality library empty. Triggering Gemini Creator...")
            from llm_provider import generate_ai_image
            from services.asset_library_service import register_asset
            
            gen_path = generate_ai_image(visual_intent)
            if gen_path:
                new_asset = register_asset(db, job.brand_id, gen_path, category="lifestyle_photos")
                if new_asset:
                    primary_id = new_asset.id
                    print(f"    [ArtDirector] SUCCESS: AI Image generated and assigned.")
        
        # v8.66: Optimized Recovery Floor (0.45) for better library usage
        if not primary_id and asset_candidates:
            best_score = asset_candidates[0][1]
            if best_score > 0.45:
                print(f"    [ArtDirector] RECOVERY: Using confident semantic match ({best_score}): {asset_candidates[0][0].id}")
                primary_id = asset_candidates[0][0].id
            else:
                print(f"    [ArtDirector] RECOVERY ABORTED: Best match ({best_score}) below 0.45. Triggering AI.")

        # Persistir en Memoria Visual Absoluta y DB (v8.1)
        # Sincronización DB-PDF: assigned_image DEBE ser el basename para el renderer
        slide.assigned_image = None
        if primary_id:
            asset_rec = db.query(models.BrandAsset).get(primary_id)
            if asset_rec:
                slide.assigned_image = os.path.basename(asset_rec.local_path)
        
        # v8.80: Merge Art Director reasoning into planning_json
        current_planning = slide.planning_json or {}
        current_planning["art_director"] = {
            "selected_asset": primary_id,
            "logic": "Library Recovery" if not job.allow_ai_images else "Primary Selection/AI",
            "threshold": 0.45
        }
        slide.planning_json = current_planning
        
        if primary_id: used_assets.append(primary_id)
        if accent_id: used_assets.append(accent_id)

        # Determinar contraste y tipografía (v5.7 - Color Corporativo Re-Fixed)
        current_title_color = p_color if p_color else "#0052A3"
        current_body_color = dna_record.text_main_color if dna_record else "#111111"
        current_font = dna_record.primary_font if dna_record and dna_record.primary_font else "Arial"
        
        if grammar_type in ["impact_number", "full_brand_overlay", "section_break"]:
            current_title_color = dna_record.text_on_dark if dna_record else "#FFFFFF"
            current_body_color = dna_record.text_on_dark if dna_record else "#FFFFFF"

        primary_asset_data = None
        if primary_id:
            asset_rec = db.query(models.BrandAsset).get(primary_id)
            if asset_rec:
                primary_asset_data = {"type": "image", "source": os.path.basename(asset_rec.local_path)}
        
        if not primary_asset_data and strategy.get("requires_hero"):
            placeholder = get_placeholder_image(visual_intent)
            primary_asset_data = {"type": "placeholder", "source": placeholder["local_path"], "text": placeholder["text_overlay"]}

        # Construir elementos de renderizado
        estimated_lines = max(1, len(slide.title) // 35 + 1)
        s_w = dna_record.slide_width_inches if dna_record else 13.33
        s_h = dna_record.slide_height_inches if dna_record else 7.5
        geo = get_layout_geometry(grammar_type, s_w, s_h, title_lines=estimated_lines)
        
        render_elements = build_decorator_elements(grammar_type, p_color, s_color)
        
        # Inyectar Logo Oficial
        if logo_path:
            render_elements.append({
                "type": "logo", "role": "logo", "path": logo_path,
                "geometry": {"top": 4.0, "left": 88.0, "width": 10.0, "height": 10.0}
            })

        # Título
        render_elements.append({
            "type": "text", "role": "title", "content": slide.title,
            "geometry": geo["title"],
            "style": {"size": 42, "bold": True, "color": current_title_color, "font": current_font}
        })

        # Cuerpo
        bullets = slide.content_json.get("bullets", [])
        if bullets and geo.get("content"):
            render_elements.append({
                "type": "text", "role": "body", "content": "\n".join([f"• {b}" for b in bullets]),
                "geometry": geo["content"], 
                "style": {"size": 22, "color": current_body_color, "font": dna_record.secondary_font if dna_record and dna_record.secondary_font else "Arial"}
            })

        # Imagen o Placeholder
        if primary_asset_data and geo.get("image"):
            if primary_asset_data["type"] == "image":
                render_elements.append({
                    "type": "image", "role": geo["image"].get("role", "supporting"),
                    "source": primary_asset_data["source"], "geometry": geo["image"]
                })
            else:
                render_elements.append({
                    "type": "shape", "role": "placeholder_bg",
                    "geometry": geo["image"], "style": {"color": p_color, "opacity": 0.1}
                })
                render_elements.append({
                    "type": "text", "role": "placeholder_text",
                    "content": primary_asset_data["text"], "geometry": geo["image"],
                    "style": {"size": 14, "color": p_color, "bold": True}
                })

        slide.render_elements = {
            "grammar_type": grammar_type,
            "elements": render_elements
        }
        slide.status = "planned"
        db.commit()

    return True
