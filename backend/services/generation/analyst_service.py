import os
import json
import models
from sqlalchemy.orm import Session
from providers.llm_provider import generate_json

DEFAULT_LAYOUT_DIVERSITY_WINDOW = 6


def get_layout_diversity_window(db: Session) -> int:
    """
    Cuántas slides previas (con layout_slug ya asignado) se muestran al Analyst
    y al Art Director para razonar sobre variedad real de layout en todo el
    deck — no solo evitar repetir el inmediato anterior. Compartido por ambos
    para que vean exactamente el mismo ritmo de deck (system_configs.
    layout_diversity_window). Nunca rompe el flujo: config ausente/corrupta
    cae al default duro.
    """
    cfg = db.query(models.SystemConfig).filter(
        models.SystemConfig.key == "layout_diversity_window"
    ).first()
    try:
        return int(cfg.value) if cfg else DEFAULT_LAYOUT_DIVERSITY_WINDOW
    except (TypeError, ValueError):
        return DEFAULT_LAYOUT_DIVERSITY_WINDOW


def get_recent_layout_history(db: Session, job_id: int, before_slide_number: int, window: int = None) -> list:
    """
    layout_slug de las últimas `window` slides antes de before_slide_number que
    ya tienen uno asignado, en orden cronológico (más antigua primero).
    Hallazgo (Synthesis Studio v2, Phase 2): con el bug de vocabulario ya
    resuelto (Findings 1/2), el Analyst seguía sin ver esto — decidía cada
    slide de forma aislada, sin saber que ya eligió 'pillars' 7 veces antes.
    """
    if window is None:
        window = get_layout_diversity_window(db)
    recent = (
        db.query(models.PresentationSlide)
        .filter(
            models.PresentationSlide.job_id == job_id,
            models.PresentationSlide.slide_number < before_slide_number,
            models.PresentationSlide.layout_slug.isnot(None),
        )
        .order_by(models.PresentationSlide.slide_number.desc())
        .limit(window)
        .all()
    )
    return [s.layout_slug for s in reversed(recent)]


def get_slide_visual_strategy(db: Session, slide: models.PresentationSlide, job: models.GenerationJob, is_premium: bool = False) -> dict:
    """
    ANALYST SERVICE v1.0 — Strategic pre-planning.
    Analyzes slide content + RAG context to define a visual mission.
    """
    print(f"    [Analyst] Defining visual strategy for slide {slide.slide_number}...")

    # 1. Obtener Prompt del Analista (v4→v3→v2→v1 fallback)
    prompt_tpl = db.query(models.SystemConfig).filter(models.SystemConfig.key == "prompt_analyst_v4").first()
    if not prompt_tpl:
        prompt_tpl = db.query(models.SystemConfig).filter(models.SystemConfig.key == "prompt_analyst_v3").first()
    if not prompt_tpl:
        prompt_tpl = db.query(models.SystemConfig).filter(models.SystemConfig.key == "prompt_analyst_v2").first()
    if not prompt_tpl:
        prompt_tpl = db.query(models.SystemConfig).filter(models.SystemConfig.key == "prompt_analyst_v1").first()
    if not prompt_tpl:
        return {"visual_intent": "General", "suggested_keywords": [slide.title], "requires_hero": True}

    # 2. RAG Context (v4.0 - Slide Specific)
    # Por ahora usamos el content_json como base, pero aquí es donde se expandiría con RAG real
    rag_context = slide.content_json.get("rag_source", "General strategic background.")

    # v9.0: historial real de layouts del deck — placeholder nuevo, str.format()
    # ignora kwargs no referenciados así que _v3/_v2/_v1 lo reciben sin romperse.
    recent_layouts = get_recent_layout_history(db, job.id, slide.slide_number)
    recent_layouts_display = json.dumps(recent_layouts) if recent_layouts else "[] (no previous slide has a layout assigned yet)"

    # 3. Ejecución de la IA
    prompt = prompt_tpl.value.format(
        slide_title=slide.title,
        bullets=str(slide.content_json.get("bullets", [])),
        rag_context=rag_context,
        recent_layouts=recent_layouts_display
    )
    
    try:
        if is_premium:
            from providers.llm_provider import generate_premium_json
            strategy = generate_premium_json(prompt)
        else:
            strategy = generate_json(prompt)
        if not strategy or not isinstance(strategy, dict):
            raise ValueError("Invalid strategy JSON")
    except Exception as e:
        print(f"    [Error] Analyst failed: {e}")
        return {"visual_intent": "General", "suggested_keywords": [slide.title], "requires_hero": True}
    
    # Robustness Check
    if isinstance(strategy, list) and len(strategy) > 0:
        strategy = strategy[0]
    
    return strategy
