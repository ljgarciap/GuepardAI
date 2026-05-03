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
    print(f"  [ContentService] Searching RAG context for Job {job_id}...")
    rag_context = search_rag(topic, knowledge_source)
    
    # 2. Obtener Guía de Tono
    tone_guideline = "Professional executive tone."
    dna = db.query(models.BrandVisualDna).filter(models.BrandVisualDna.source_filename == style_slug).first()
    if dna and dna.raw_extraction:
        tone_guideline = dna.raw_extraction.get("tone_description", tone_guideline)
    
    # 3. Prompt de Síntesis Estratégica (Dinámico v23.3)
    prompt = f"""
    ### SYSTEM ROLE: STRATEGIC MULTILINGUAL SYNTHESIZER
    ### OUTPUT LANGUAGE: {region} (Target Context)
    
    Context: {rag_context}
    Tone Guideline: {tone_guideline}
    Topic: {topic}
    
    Generate a JSON outline for this presentation. 
    IMPORTANT: Respect the number of slides requested by the user in the 'Topic' if specified. 
    If not specified, generate a complete and logical presentation (usually 10-20 slides).
    
    For each slide, provide:
    - title: Strategic title
    - bullets: 3-5 high-value points
    - objective: What is this slide trying to achieve?
    - visual_intent: A short (10 words) descriptive prompt of the ideal image for this slide.
    - visual_tags: A list of 5-7 simple, descriptive tags for image searching (e.g., ["store", "digital", "customer"]).
    
    Return ONLY JSON:
    {{ "slides": [ {{ "title": "...", "bullets": ["..."], "objective": "...", "visual_intent": "...", "visual_tags": ["tag1", "tag2", "tag3"] }} ] }}
    """
    
    print(f"  [ContentService] Calling LLM for flexible content synthesis...")
    response = generate_json(prompt)
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
                "bullets": s_data.get("bullets", []),
                "objective": s_data.get("objective", ""),
                "visual_intent": s_data.get("visual_intent", ""),
                "visual_tags": s_data.get("visual_tags", []),
                "rag_source": specific_rag # El alimento para el Analista
            },
            status="content_ready"
        )
        db.add(new_slide)
    
    db.commit()
    return True
