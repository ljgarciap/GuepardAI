import os
import json
import models
from sqlalchemy.orm import Session
from llm_provider import generate_json, get_embedding
import psycopg
from typing import List, Dict

DB_URL = os.getenv("DATABASE_URL", "postgresql://root:root@localhost:5432/ai_db").replace("+psycopg", "")

def search_rag(query: str, knowledge_source: str, k: int = 15) -> str:
    """Busca contexto en el RAG basado en similitud vectorial."""
    try:
        query_embedding = get_embedding(query)
    except Exception as e:
        print(f"  [ContentService] Embedding failed: {e}")
        return ""
    
    results = []
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT content, 1 - (embedding <=> %s::vector) as similarity
                    FROM corporate_knowledge
                    WHERE source_filename = %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (str(query_embedding), knowledge_source, str(query_embedding), k)
                )
                for row in cur.fetchall():
                    results.append(row[0])
    except Exception as e:
        print(f"  [ContentService] Postgres Vector error: {e}")
        return ""
    
    return "\n---\n".join(results)

def synthesize_presentation_outline(db: Session, job_id: int, req_data: dict) -> bool:
    """
    FASE 1: Generación de Contenido (RAG + LLM).
    Crea las slides en la DB con su contenido textual.
    """
    job = db.query(models.GenerationJob).get(job_id)
    if not job: return False
    
    topic = req_data.get("prompt")
    style_slug = req_data.get("style_filename")
    knowledge_source = req_data.get("knowledge_filename")
    region = req_data.get("region", "Global")
    allow_ai_images = req_data.get("allow_ai_images", False)
    
    # 0. Actualizar el Job con el permiso (v7.0)
    job.allow_ai_images = allow_ai_images
    db.commit()
    print(f"  [ContentService] Searching RAG context for Job {job_id} (DENSE MODE: k=60)...")
    rag_context = search_rag(topic, knowledge_source, k=60)
    
    # 2. Obtener Guía de Tono
    tone_guideline = "Professional executive tone."
    dna = db.query(models.BrandVisualDna).filter(models.BrandVisualDna.source_filename == style_slug).first()
    if dna and dna.raw_extraction:
        tone_guideline = dna.raw_extraction.get("tone_description", tone_guideline)
    
    # 3. Obtener Configs de Marca y Agencia (v24.0)
    cfg_architect = db.query(models.SystemConfig).filter(models.SystemConfig.key == "prompt_architect_v1").first()
    cfg_synthesizer = db.query(models.SystemConfig).filter(models.SystemConfig.key == "prompt_content_synthesizer_v2").first()
    agency_name = db.query(models.SystemConfig).filter(models.SystemConfig.key == "agency_name").first()
    
    brand_name = "Global Strategy"
    if dna and dna.brand:
        brand_name = dna.brand.name

    # --- PASO 1: ARQUITECTO DE PROMPTS ---
    # Este paso pule el prompt del usuario y le da prioridad absoluta
    print(f"  [ContentService] Step 1/2: Invoking Prompt Architect...")
    architect_prompt = cfg_architect.value.format(
        topic=topic,
        brand_name=brand_name,
        tone_guideline=tone_guideline
    )
    # Usamos un modelo más potente si está disponible para el arquitecto
    architect_response = generate_json(architect_prompt, specialization="general")
    
    # DEFENSIVE: Handle cases where the LLM might return a list or a dict
    if isinstance(architect_response, dict):
        polished_prompt = architect_response.get("polished_instruction", str(architect_response))
    else:
        polished_prompt = str(architect_response)

    # --- PASO 2: SINTETIZADOR DE CONTENIDO ---
    # Usa la instrucción pulida y el RAG para generar los slides
    print(f"  [ContentService] Step 2/2: Calling Strategic Synthesizer v2.0...")
    final_prompt = cfg_synthesizer.value.format(
        polished_prompt=polished_prompt,
        rag_context=rag_context,
        target_lang=region
    )
    
    response = generate_json(final_prompt)
    
    # DEFENSIVE: Gemini 2.5+ sometimes returns a list directly instead of {"slides": [...]}
    if isinstance(response, list):
        slides_data = response
    else:
        slides_data = response.get("slides", [])
    
    print(f"  [ContentService] Saving {len(slides_data)} slides with Slide-Specific RAG...")
    # Limpiar si ya existen (por reintentos)
    db.query(models.PresentationSlide).filter(models.PresentationSlide.job_id == job_id).delete()
    
    for i, s_data in enumerate(slides_data):
        # RAG QUIRÚRGICO: Por cada slide, buscamos su contexto específico
        slide_title = s_data.get("title", "Untitled Slide")
        print(f"    [ContentService] Harvesting specific RAG for: {slide_title}...")
        specific_rag = search_rag(slide_title, knowledge_source, k=5)

        new_slide = models.PresentationSlide(
            job_id=job_id,
            slide_number=i + 1,
            title=slide_title,
            content_json={
                "title": slide_title,
                "bullets": s_data.get("bullets", []),
                "metrics": s_data.get("metrics", []),
                "section_label": s_data.get("section_label", "STRATEGY"),
                "layout_type": s_data.get("layout_type"),
                "objective": s_data.get("objective", ""),
                "visual_intent": s_data.get("visual_intent", ""),
                "visual_tags": s_data.get("visual_tags", []),
                "metadata": s_data.get("metadata") if isinstance(s_data.get("metadata"), dict) else {},
                "rag_source": specific_rag
            },
            planning_json={
                "strategy": "Initial Synthesis",
                "objective": s_data.get("objective", "Create strategic summary")
            },
            status="content_ready"
        )
        db.add(new_slide)
    
    db.commit()
    
    # ── DECOUPLED V11: Build ContentManifest to pass downstream ──
    from schemas.presentation import ContentManifest, ContentManifestSlide
    slides = []
    
    # Fetch from DB to ensure IDs and states are correct, though we could build it in memory
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
        
    return ContentManifest(
        job_id=job_id,
        slides=slides,
        client_name=None
    )
