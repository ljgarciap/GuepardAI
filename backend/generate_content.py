import sys
import json
import psycopg
from llm_provider import generate_json, get_embedding
import os
from dotenv import load_dotenv

DB_CONN = os.getenv("DATABASE_URL", "postgresql://root:root@localhost:5432/ai_db").replace("+psycopg", "")

REGION_LANG_MAP = {
    "LATAM": "SPANISH (Latin America)",
    "ES": "SPANISH (Spain)",
    "UK": "BRITISH ENGLISH (UK)",
    "USA": "AMERICAN ENGLISH (USA)",
    "Global": "INTERNATIONAL ENGLISH"
}

def search_rag(query, knowledge_source, k=15):
    try:
        query_embedding = get_embedding(query)
    except Exception as e:
        print(f"Error generando embedding del query: {e}")
        return ""
    
    results = []
    try:
        with psycopg.connect(DB_CONN) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT content, 1 - (embedding <=> %s::vector) as similarity
                    FROM corporate_knowledge
                    WHERE metadata->>'source' = %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (str(query_embedding), knowledge_source, str(query_embedding), k)
                )
                for row in cur.fetchall():
                    results.append(row[0])
    except Exception as e:
        print(f"Error conectando a Postgres Vector para RAG: {e}")
        return ""
    
    # Uniremos los 15 fragmentos para darle una ventana de contexto masiva
    return "\n---\n".join(results)

def generate_presentation_outline(topic, style_slug, knowledge_source, region="Global"):
    print(f"Searching RAG context for: '{topic}' strictly from source file: '{knowledge_source}'...")
    rag_context = search_rag(topic, knowledge_source)
    
    if not rag_context or len(rag_context) < 300:
        raise ValueError(f"Insufficient RAG context for topic '{topic}' in file '{knowledge_source}'.")
    
    print(f"Loading Design DNA Tone for style slug: '{style_slug}'...")
    tone_guideline = "Maintain a professional and direct executive tone."
    try:
        from database import SessionLocal
        import models
        db = SessionLocal()
        brand = db.query(models.BrandStyle).filter(models.BrandStyle.style_slug == style_slug).first()
        if brand and brand.tone_description:
            tone_guideline = brand.tone_description
    except Exception as e:
        print(f"Failed to fetch tone from DB, using default: {e}")
        
    target_lang = REGION_LANG_MAP.get(region, "NEUTRAL ENGLISH")

    
    prompt = f"""
    ### SYSTEM ROLE: STRATEGIC MULTILINGUAL SYNTHESIZER
    ### OUTPUT LANGUAGE: {target_lang} (MANDATORY)
    
    You are a professional consultant transforming English RAG context into brand-aligned regional content.
    
    ### CONSTRAINTS (VIOLATION = SYSTEM SHUTDOWN):
    1. LANGUAGE ENFORCEMENT: 
       - Current Region: {region}
       - You MUST translate everything into {target_lang}. 
       - Output JSON values MUST be in the target language.
    
    2. LAYOUT CATALOG (DIVERSITY REQUIRED):
       - 'composition_hero': Cover/Intro slides.
       - 'composition_split': Standard content (Image + Bullets).
       - 'composition_pillars': Exactly 3 key items.
       - 'composition_quote': One powerful executive statement/quote.
       - 'composition_grid': Exactly 4 items (2x2 matrix).
       - 'big_metric': Single KPI (Requires 'metric' and 'label').
    
    3. SOURCE FIDELITY: 
       - Context: {rag_context}
    
    ### RENDERING INSTRUCTIONS:
    - Choose Layouts: Mix them up! Do not repeat 'split' more than 3 times in a row.
    - Title Limits: Max 40 chars. 
    - Bullet Limits: Max 80 chars. 
    - Visual Diversity: Unique 4-word image_prompt for EVERY slide.
    
    ### DESIGN TONE DIRECTIVES:
    {tone_guideline}
    
    ### JSON TEMPLATE:
    {{
      "slides": [
        {{
          "slide_number": 1,
          "layout_type": "...",
          "title": "...",
          "bullets": ["..."],
          "metric": "...",
          "label": "...",
          "image_prompt": "..."
        }}
      ]
    }}
    
    ### FINAL CHECK:
    - IS THE OUTPUT IN {target_lang}? 
    - Does it align with the strategic visual tone provided?
    - If YES, output the JSON now.
    """
    
    print(f"Compiling Strategic Intelligence from {knowledge_source} crossed with {style_slug}...")
    return generate_json(prompt)

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python generate_content.py '<topic_prompt>' <style_slug> <knowledge_source_file>")
        sys.exit(1)
        
    topic = sys.argv[1]
    style_slug = sys.argv[2]
    knowledge_source = sys.argv[3]
    
    result = generate_presentation_outline(topic, style_slug, knowledge_source)
    
    out_file = "content.json"
    with open(out_file, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        
    print(f"\nSuccess! Outline compiled and saved to {os.path.abspath(out_file)}.")
