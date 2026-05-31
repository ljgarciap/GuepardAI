import os
import json
import random
import datetime
import models
import time
from sqlalchemy.orm import Session
from providers.llm_provider import generate_json, generate_ai_image
from services.assets.asset_library_service import find_best_assets
from services.generation.analyst_service import get_slide_visual_strategy
from services.rendering.placeholder_service import get_placeholder_image
from services.ingestion.brand_composition_dna import get_layout_geometry, build_decorator_elements
from services.rendering.font_service import ensure_brand_fonts

def plan_presentation_design(db: Session, job_id: int, is_premium: bool = False):
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
        strategy = get_slide_visual_strategy(db, slide, job, is_premium=is_premium)
        visual_intent = strategy.get("visual_intent", "Executive")

        # Inyectar esencia artística del manual de marca (v10.0 Replit-Upgrade)
        essence = db.query(models.BrandArtisticEssence).filter(models.BrandArtisticEssence.brand_id == job.brand_id).first()
        art_direction_note = essence.art_direction_note if essence else "Maintain a clean, professional corporate style."
        
        # Inyectar Patrones Premium disponibles (v15.0)
        premium_patterns = db.query(models.BrandPremiumVisualPattern).filter(models.BrandPremiumVisualPattern.brand_id == job.brand_id).all()
        premium_layout_options = []
        if premium_patterns:
            for p in premium_patterns:
                if p.patterns_json:
                    for pattern_dict in p.patterns_json:
                        if isinstance(pattern_dict, dict) and "pattern_type" in pattern_dict:
                            premium_layout_options.append(pattern_dict["pattern_type"])
        if premium_layout_options:
            art_direction_note += f"\n\nCRITICAL LAYOUT OVERRIDE PERMISSION: You are HIGHLY ENCOURAGED to override the basic grammar_type using one of the following premium layouts extracted from the brand's DNA: {', '.join(premium_layout_options)}. Choose the one that best fits the slide content."
            
        # Filtro semántico anti-competidores
        art_direction_note += f"\n\nCRITICAL BRAND SAFETY: If any asset in the 'found_assets' list belongs to a direct competitor (e.g., a competitor's logo or store), DO NOT select it under any circumstances. Always prioritize assets that belong specifically to the brand we are designing for."
        
        # v8.0: El Analista decide el grammar_type — el Art Director lo respeta
        analyst_grammar_type = strategy.get("grammar_type", "composition_split")

        # Enriquecer content_json del slide con lo que detectó el Analista (v8.0)
        if strategy.get("metric_value") and not slide.content_json.get("metric"):
            content = dict(slide.content_json or {})
            content["metric"] = strategy["metric_value"]
            slide.content_json = content
            db.commit()
        
        # FASE B: BÚSQUEDA EN CASCADA (Protocolo v6.0)
        from services.assets.asset_library_service import find_assets_by_tags
        
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
                    from providers.llm_provider import generate_ai_image
                    from services.assets.asset_library_service import register_asset
                    
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
        # Consideramos split también como hi-res requirements para evitar estiramientos
        requires_hi_res = suggested_layout in ["hero", "full_brand_overlay", "big_image", "full_bleed"] or "split" in suggested_layout
        
        for asset, score in asset_candidates:
            asset_info = {
                "id": asset.id, 
                "score": score, 
                "category": asset.category, 
                "desc": asset.description[:80],
                "path": os.path.basename(asset.local_path)
            }
            
            # REGLA DE CALIDAD ESTRICTA: No logos ni íconos como imágenes de fondo
            if requires_hi_res and asset.category in ["logos", "icons"]:
                audit_metadata["rejected"].append({"reason": "Category forbidden for background", **asset_info})
                continue
            
            # REGLA DE CALIDAD v8.9: Verificación Física si no hay Metadata
            res_ok = True
            min_required = 1200 if requires_hi_res else 800
            
            w, h = asset.width, asset.height
            if not w and asset.local_path and os.path.exists(asset.local_path):
                try:
                    with Image.open(asset.local_path) as img:
                        w, h = img.size
                except: pass

            if w and w < min_required:
                res_ok = False
                audit_metadata["rejected"].append({"reason": f"Resolution too low ({w}px < {min_required}px)", **asset_info})
            elif requires_hi_res and not w:
                # v8.9.1: If dimensions are unknown and hi-res is required, reject it to prevent massive pixelation
                res_ok = False
                audit_metadata["rejected"].append({"reason": f"Unknown dimensions for hi-res layout", **asset_info})

            if score >= 0.40 and res_ok: 
                filtered_assets.append(asset_info)
                audit_metadata["considered"].append(asset_info)
            else:
                audit_metadata["rejected"].append(asset_info)

        # FASE C: DIRECCIÓN DE ARTE (Ejecución con Memoria Visual)
        visual_history = []
        # Traer layouts recientes (v5.0 Variety Enforcement)
        recent_slides = db.query(models.PresentationSlide).filter(
            models.PresentationSlide.job_id == job_id,
            models.PresentationSlide.slide_number < slide.slide_number,
            models.PresentationSlide.layout_slug != None
        ).order_by(models.PresentationSlide.slide_number.desc()).limit(3).all()
        
        recent_layouts = [s.layout_slug for s in reversed(recent_slides)]
        visual_history.append(f"Recent layouts used: {recent_layouts}")
        
        for uid in used_assets:
            u_asset = db.query(models.BrandAsset).get(uid)
            if u_asset: visual_history.append(f"Used Asset: {u_asset.description[:100]}")

        # Extraer JSONs crudos para inyectarlos en el prompt
        vision_dna_json = json.dumps(essence.raw_vision_response, indent=2) if essence and essence.raw_vision_response else "{}"
        
        premium_patterns_json_list = []
        if premium_patterns:
            for p in premium_patterns:
                if p.patterns_json:
                    premium_patterns_json_list.extend(p.patterns_json)
        premium_patterns_json_str = json.dumps(premium_patterns_json_list, indent=2) if premium_patterns_json_list else "[]"

        safe_p_color = str(p_color) if p_color else "#0052A3"
        safe_s_color = str(s_color) if s_color else "#EE1C2E"
        safe_font = str(dna_record.primary_font) if dna_record and dna_record.primary_font else "Arial"
        safe_title = str(slide.title) if slide.title else "Slide"
        safe_art_note = str(art_direction_note) if art_direction_note else "Maintain a clean, professional corporate style."

        prompt = prompt_tpl.value \
            .replace("{visual_strategy}", json.dumps(strategy)) \
            .replace("{primary_color}", safe_p_color) \
            .replace("{secondary_color}", safe_s_color) \
            .replace("{primary_font}", safe_font) \
            .replace("{slide_title}", safe_title) \
            .replace("{bullets}", str(slide.content_json.get("bullets", []))) \
            .replace("{found_assets}", json.dumps(filtered_assets)) \
            .replace("{visual_history}", json.dumps(visual_history)) \
            .replace("{art_direction_note}", safe_art_note) \
            .replace("{vision_dna_json}", vision_dna_json) \
            .replace("{premium_patterns_json}", premium_patterns_json_str)
        
        if is_premium:
            from providers.llm_provider import generate_premium_json
            decision = generate_premium_json(prompt)
        else:
            from providers.llm_provider import generate_json
            decision = generate_json(prompt)
        
        # Robustness check
        if isinstance(decision, list) and len(decision) > 0: decision = decision[0]
        
        # FASE D: AUDITORÍA (Bitácora)
        raw_reasoning = decision.get("visual_reasoning") or decision.get("reasoning", "Strategic choice.")
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
        
        # v12.0: Layout Override (Soledad del Diseñador)
        layout_override = decision.get("suggested_layout_override")
        if layout_override:
            print(f"    [ArtDirector] LAYOUT OVERRIDE: {grammar_type} -> {layout_override}")
            grammar_type = layout_override
            slide.layout_slug = layout_override

        # GUARDIA DE HIERRO (v8.5) - Prioridad Library y No Repetición
        valid_ids = [a["id"] for a in filtered_assets]
        
        if (not primary_id or primary_id not in valid_ids) and filtered_assets:
            print(f"    [ArtDirector] FORCING: LLM rejected/missed candidates. Using best library match: {filtered_assets[0]['id']}")
            primary_id = filtered_assets[0]["id"]
        
        # FASE E.2: THE CREATOR (v8.5) - Solo si de verdad NO hay nada en la librería de calidad
        if not primary_id and job.allow_ai_images:
            print(f"    [ArtDirector] ACTION: Quality library empty. Triggering Gemini Creator...")
            from providers.llm_provider import generate_ai_image
            from services.assets.asset_library_service import register_asset
            
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

        # Persistir en Memoria Visual Absoluta y DB (v10.0 - Icon Support via planning_json)
        slide.assigned_image = None
        
        # v23.8: Safe icon storage in planning_json to avoid DB schema mismatches
        current_planning = slide.planning_json or {}
        current_planning["bullet_icon"] = None
        
        if primary_id:
            asset_rec = db.query(models.BrandAsset).get(primary_id)
            if asset_rec:
                slide.assigned_image = os.path.basename(asset_rec.local_path)
        
        if accent_id:
            accent_rec = db.query(models.BrandAsset).get(accent_id)
            if accent_rec:
                # Resolver path para el bullet icon (Base64) - Guardado en planning_json para estabilidad
                current_planning["bullet_icon"] = os.path.basename(accent_rec.local_path)
        
        # v8.80: Merge Art Director reasoning into planning_json
        current_planning = slide.planning_json or {}
        current_planning["art_director"] = {
            "selected_asset": primary_id,
            "logic": "Designer Mode v3.0",
            "reasoning": raw_reasoning,
            "layout_override": layout_override,
            "canvas_elements": decision.get("canvas_elements", []),
            "threshold": 0.45,
            "timestamp": datetime.datetime.utcnow().isoformat()
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
