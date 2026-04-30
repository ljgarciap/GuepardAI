import os
import json
import psycopg
from llm_provider import generate_json, get_embedding

DB_CONN = os.getenv("DATABASE_URL", "postgresql://root:root@localhost:5432/ai_db").replace("+psycopg", "")

REGION_LANG_MAP = {
    "LATAM": "SPANISH (Latin America)",
    "ES": "SPANISH (Spain)",
    "UK": "BRITISH ENGLISH (UK)",
    "USA": "AMERICAN ENGLISH (USA)",
    "Global": "INTERNATIONAL ENGLISH"
}

def search_rag(query, brand_id=None, k=15):
    """
    Búsqueda Semántica Soberana (v11.0).
    Filtra estrictamente por el brand_id oficial.
    """
    try:
        query_embedding = get_embedding(query)
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return ""
    
    results = []
    try:
        with psycopg.connect(DB_CONN) as conn:
            with conn.cursor() as cur:
                # v11.0: Gobernanza de Marca Híbrida (Exclusivo + Público)
                if brand_id == -1:
                    # Modo Superuser: Buscar en todo el universo de datos
                    cur.execute(
                        """
                        SELECT content FROM corporate_knowledge
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s
                        """,
                        (str(query_embedding), k)
                    )
                else:
                    # Modo Soberano: Buscar exclusivo de marca O público
                    cur.execute(
                        """
                        SELECT content FROM corporate_knowledge
                        WHERE brand_id = %s OR is_public = 1
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s
                        """,
                        (brand_id, str(query_embedding), k)
                    )
                for row in cur.fetchall():
                    results.append(row[0])
    except Exception as e:
        print(f"Error RAG: {e}")
        return ""
    return "\n---\n".join(results)

def plan_narrative(topic: str) -> list:
    """
    NARRATIVE ARCHITECT (v12.0).
    Decompounds the user prompt into strategic search axes.
    """
    prompt = f"""
    You are a Strategic Planner. Decompound the following presentation request into 3 to 5 specific search queries to retrieve high-quality corporate data from a knowledge base.
    
    USER REQUEST: {topic}
    
    Example output for "Tesco Strategy":
    ["Tesco Brand Values and Mission", "Clubcard and Loyalty Program performance", "Tesco Market Share and Competitors", "Financial results and ESG commitments"]
    
    RESPONSE ONLY with this JSON format:
    {{ "queries": ["query 1", "query 2", ...] }}
    """
    try:
        plan = generate_json(prompt, specialization="general")
        return plan.get("queries", [topic])
    except:
        return [topic]

def synthesize_strategic_content(topic, brand_id, region="Global"):
    print(f"[ContentEngine] Orchestrating Narrative Architecture for: {topic}", flush=True)
    
    # 1. Narrative Planning
    search_axes = plan_narrative(topic)
    print(f"[ContentEngine] Search Axes: {search_axes}", flush=True)
    
    # 2. Multi-Query RAG
    rag_blocks = []
    for axis in search_axes:
        print(f"  [RAG] Searching for Axis: {axis}...", flush=True)
        block = search_rag(axis, brand_id)
        if block:
            rag_blocks.append(f"### DATA FOR: {axis}\n{block}")
    
    rag_context = "\n\n".join(rag_blocks)

    if not rag_context:
        raise ValueError(f"No RAG content found for Brand ID '{brand_id}'. "
                         "Please ensure the strategic documents have been ingested for this brand first.")

    target_lang = REGION_LANG_MAP.get(region, "NEUTRAL ENGLISH")

    prompt = f"""
You are a Corporate Strategy Director with expertise in high-level executive presentations.

USER INSTRUCTION:
{topic}

MANDATORY OUTPUT LANGUAGE: {target_lang}

COMPANY CONTEXT (extracted from knowledge base):
{rag_context}

YOUR MISSION:
Generate a professional strategic presentation based ONLY on the context provided above.
- DO NOT invent data that is not in the context.
- If the user specified a number of slides, respect it. Otherwise, use between 10 and 15 slides.
- Content must be concise, result-oriented, and appropriate for executive levels.
- Each slide must have a clear purpose and contribute to the overall narrative.

LAYOUT INTENT FORMAT (choose the most appropriate per slide):
- 'hero'        → Strong visual impact slide, powerful phrase
- 'split'       → Text on left, image/data on right
- 'content'     → Main textual content with bullets
- 'data'        → Metrics or highlighted data
- 'quote'       → Quote or testimonial
- 'grid'        → Multiple elements in a grid
- 'conclusion'  → Closing or call to action

RESPONSE ONLY with this JSON (no additional text outside the JSON):
{{
  "slides": [
    {{
      "slide_number": 1,
      "layout_intent": "hero",
      "title": "Impactful slide title",
      "bullets": ["Strategic point 1", "Strategic point 2", "Strategic point 3"],
      "metric": "Key data if applicable, otherwise null",
      "image_narrative": "3-4 specific keywords for a HIGH-END CORPORATE image. STRICTLY FORBIDDEN: metaphors, puzzles, gears, handshakes, or abstract concepts. USE ONLY: 'modern retail store', 'executive boardroom', 'data center', 'logistics hub', 'city skyline', or 'professional team at work'."
    }}
  ]
}}
"""
    print(f"[ContentEngine] Synthesizing in {target_lang}...", flush=True)
    manifest = generate_json(prompt, specialization="general")
    
    # --- INTEGRITY FILTER (v29.1) ---
    clean_slides = []
    for s in manifest.get("slides", []):
        if s.get("title") and (s.get("bullets") or s.get("metric")):
            clean_slides.append(s)
            
    manifest["slides"] = clean_slides
    print(f"[ContentEngine] Manifest Validated: {len(clean_slides)} slides passed integrity.")
    return manifest, prompt

if __name__ == "__main__":
    # Test
    res = synthesize_strategic_content("Clubcard strategy", "Tesco", "LATAM")
    print(json.dumps(res, indent=2))
