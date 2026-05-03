import os
import json
import models
import time
from sqlalchemy.orm import Session
from llm_provider import generate_json
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
        
        # FASE B: BÚSQUEDA Y SCORING DE ASSETS (Limit 12 para más variedad)
        search_keywords = strategy.get("suggested_keywords", [slide.title])
        asset_candidates = find_best_assets(db, job.brand_id, search_keywords, limit=12, exclude_ids=used_assets)
        
        # Filtrar assets por umbral y jerarquía
        filtered_assets = []
        audit_metadata = {"considered": [], "rejected": []}
        
        for asset, score in asset_candidates:
            asset_info = {"id": asset.id, "score": score, "category": asset.category, "desc": asset.description[:50]}
            
            # REGLA DE ORO ESTRICTA (v5.1)
            is_valid_hero = asset.category in ["lifestyle_photos", "backgrounds"] and score >= THRESHOLD
            is_valid_accent = asset.category in ["design_elements", "logos"] and score >= (THRESHOLD - 0.1)
            
            if is_valid_hero or is_valid_accent:
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
        if isinstance(raw_reasoning, dict):
            raw_reasoning = json.dumps(raw_reasoning)

        audit = models.ArtDirectorDecision(
            job_id=job_id,
            slide_number=slide.slide_number,
            decision_type="layout_selection",
            summary=f"Intent: {visual_intent}",
            reasoning=raw_reasoning,
            prompt_used=prompt,
            response_raw=json.dumps(decision),
            metadata_json=audit_metadata
        )
        db.add(audit)

        # FASE E: ENSAMBLAJE DEL MANIFIESTO
        grammar_type = decision.get("grammar_type", "strategic_split")
        primary_id = decision.get("primary_asset_id")
        
        # Determinar contraste según el layout (v5.0)
        current_text_color = dna_record.text_main_color if dna_record else "#111111"
        if grammar_type in ["impact_number", "full_brand_overlay"]:
            current_text_color = dna_record.text_on_dark if dna_record else "#FFFFFF"

        primary_asset_data = None
        if primary_id:
            used_assets.append(primary_id)
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
        
        # Inyectar Logo Oficial (v4.6 - Identidad Corporativa)
        if logo_path:
            render_elements.append({
                "type": "logo", "role": "logo", "path": logo_path,
                "geometry": {"top": 4.0, "left": 88.0, "width": 10.0, "height": 10.0} # 10% del canvas
            })

        # Título
        render_elements.append({
            "type": "text", "role": "title", "content": slide.title,
            "geometry": geo["title"],
            "style": {"size": 42, "bold": True, "color": current_text_color, "font": dna_record.primary_font if dna_record else "Arial"}
        })

        # Cuerpo
        bullets = slide.content_json.get("bullets", [])
        if bullets and geo.get("content"):
            render_elements.append({
                "type": "text", "role": "body", "content": "\n".join([f"• {b}" for b in bullets]),
                "geometry": geo["content"], 
                "style": {"size": 20, "color": current_text_color, "font": dna_record.secondary_font if dna_record and dna_record.secondary_font else "Arial"}
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
