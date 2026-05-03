import datetime
import os
import json
from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models

def seed_data():
    db = SessionLocal()
    try:
        # 1. Configuración de Modelos y API
        configs = [
            {
                "key": "asset_score_threshold",
                "value": "0.70",
                "description": "Umbral mínimo de similitud (0.0 a 1.0) para aceptar un asset de marca."
            },
            {
                "key": "embedding_model_chain",
                "value": "mistral-embed,models/text-embedding-004",
                "description": "Cadena de modelos de embedding. MISTRAL debe ser primero para mantener consistencia de 1024 dims."
            },
            {
                "key": "model_image_gen",
                "value": "imagen-3.0-generate-001",
                "description": "Modelo de Google Gemini para generación de imágenes bajo demanda (Imagen 3)."
            },
            {
                "key": "prompt_analyst_v1",
                "value": """You are a Strategic Design Analyst. 
Analyze the following slide content and define a Visual Strategy.

CONTENT:
Title: {slide_title}
Bullets: {bullets}
RAG Context: {rag_context}

YOUR GOAL:
1. Define the 'visual_intent' (Use CONCRETE OBJECTS, e.g., "A modern store with customers", NOT abstract concepts like "Innovation").
2. Identify 3-5 keywords for image search. Be specific (e.g., "shopping cart", "digital screen", "smiling person").
3. Determine if this slide requires a HERO image.

OUTPUT ONLY JSON:
{{
  "visual_intent": "...",
  "suggested_keywords": ["concrete_term1", "concrete_term2"],
  "requires_hero": true/false,
  "narrative_tone": "executive"
}}""",
                "description": "Strategic Analyst prompt v1.1 - Concrete Keywords"
            },
            {
                "key": "prompt_art_director_v1",
                "value": """You are a Senior Art Director. 
Follow the VISUAL STRATEGY: {visual_strategy}

ASSET HIERARCHY:
- 'lifestyle_photos': HERO only.
- 'design_elements': ACCENTS only.

RULES:
1. If 'primary_asset_id' is NULL (no suitable hero), you MUST use "impact_number" or "two_column" to fill the space. 
2. NEVER use "strategic_split" if there is no image.

OUTPUT ONLY JSON:
{{
  "grammar_type": "...", 
  "primary_asset_id": <int or null>, 
  "accent_asset_id": <int or null>,
  "reasoning": "..."
}}""",
                "description": "Art Director planning prompt v4.1 - Layout Adaptability"
            }
        ]

        for cfg in configs:
            existing = db.query(models.SystemConfig).filter(models.SystemConfig.key == cfg["key"]).first()
            if existing:
                existing.value = cfg["value"]
            else:
                db.add(models.SystemConfig(key=cfg["key"], value=cfg["value"]))
        
        db.commit()
        print("  [Seed] System Configs (v3.1) seeded successfully.")
    except Exception as e:
        db.rollback()
        print(f"  [Seed] Error seeding configs: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()
