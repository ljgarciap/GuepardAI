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
    
    # 1. Obtener Contexto RAG
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
    
    Return ONLY JSON:
    {{ "slides": [ {{ "title": "...", "bullets": ["..."], "objective": "...", "visual_intent": "..." }} ] }}
    """
    
    print(f"  [ContentService] Calling LLM for flexible content synthesis...")
    response = generate_json(prompt)
    slides_data = response.get("slides", [])
    
    # 4. Persistir Slides en DB
    print(f"  [ContentService] Saving {len(slides_data)} slides to DB...")
    # Limpiar si ya existen (por reintentos)
    db.query(models.PresentationSlide).filter(models.PresentationSlide.job_id == job_id).delete()
    
    for i, s_data in enumerate(slides_data):
        new_slide = models.PresentationSlide(
            job_id=job_id,
            slide_number=i + 1,
            title=s_data.get("title", "Untitled Slide"),
            content_json={
                "bullets": s_data.get("bullets", []),
                "objective": s_data.get("objective", ""),
                "visual_intent": s_data.get("visual_intent", "")
            },
            status="content_ready"
        )
        db.add(new_slide)
    
    db.commit()
    return True
