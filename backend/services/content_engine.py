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

def search_rag(query, client_name="Internal", k=15):
    try:
        query_embedding = get_embedding(query)
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return ""
    
    results = []
    try:
        with psycopg.connect(DB_CONN) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT content FROM corporate_knowledge
                    WHERE metadata->>'source' = %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (client_name, str(query_embedding), k)
                )
                for row in cur.fetchall():
                    results.append(row[0])
    except Exception as e:
        print(f"Error RAG: {e}")
        return ""
    return "\n---\n".join(results)

def synthesize_strategic_content(topic, client_name, region="Global", knowledge_source=None):
    source = knowledge_source or client_name
    print(f"[ContentEngine] Fetching RAG for: {topic} | source: {source}", flush=True)
    rag_context = search_rag(topic, source)

    if not rag_context:
        raise ValueError(f"No RAG content found for source '{source}'. "
                         "Please ensure the knowledge file has been ingested first.")

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
    print(f"[ContentEngine] Sintetizando en {target_lang}...", flush=True)
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
