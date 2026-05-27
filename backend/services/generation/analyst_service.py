import os
import json
import models
from sqlalchemy.orm import Session
from providers.llm_provider import generate_json

def get_slide_visual_strategy(db: Session, slide: models.PresentationSlide, job: models.GenerationJob) -> dict:
    """
    ANALYST SERVICE v1.0 — Strategic pre-planning.
    Analyzes slide content + RAG context to define a visual mission.
    """
    print(f"    [Analyst] Defining visual strategy for slide {slide.slide_number}...")
    
    # 1. Obtener Prompt del Analista
    prompt_tpl = db.query(models.SystemConfig).filter(models.SystemConfig.key == "prompt_analyst_v1").first()
    if not prompt_tpl:
        return {"visual_intent": "General", "suggested_keywords": [slide.title], "requires_hero": True}

    # 2. RAG Context (v4.0 - Slide Specific)
    # Por ahora usamos el content_json como base, pero aquí es donde se expandiría con RAG real
    rag_context = slide.content_json.get("rag_source", "General strategic background.")

    # 3. Ejecución de la IA
    prompt = prompt_tpl.value.format(
        slide_title=slide.title,
        bullets=str(slide.content_json.get("bullets", [])),
        rag_context=rag_context
    )
    
    try:
        from providers.llm_provider import generate_premium_json
        strategy = generate_premium_json(prompt)
        if not strategy or not isinstance(strategy, dict):
            raise ValueError("Invalid strategy JSON")
    except Exception as e:
        print(f"    [Error] Analyst failed: {e}")
        return {"visual_intent": "General", "suggested_keywords": [slide.title], "requires_hero": True}
    
    # Robustness Check
    if isinstance(strategy, list) and len(strategy) > 0:
        strategy = strategy[0]
    
    return strategy
