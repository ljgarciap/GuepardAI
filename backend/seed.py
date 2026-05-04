"""
seed.py — GuepardAI v8.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CAMBIOS v8.0:
  - prompt_analyst_v1: ahora decide grammar_type con reglas completas
  - prompt_art_director_v1: ahora solo asigna assets (no decide tipo)
  - Nuevas configs: variety rules, painter mode
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import datetime
import os
from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models


def seed_data():
    db = SessionLocal()
    try:
        configs = [

            # ─────────────────────────────────────────────────────
            # INFRAESTRUCTURA
            # ─────────────────────────────────────────────────────
            {
                "key": "asset_score_threshold",
                "value": "0.45",
                "description": "Umbral mínimo de similitud semántica para aceptar asset. 0.45 es el punto dulce para evitar logos pero permitir fotos reales."
            },
            {
                "key": "embedding_model_chain",
                "value": "mistral-embed,models/text-embedding-004",
                "description": "Cadena de modelos de embedding. MISTRAL primero para consistencia de 1024 dims."
            },
            {
                "key": "model_image_gen",
                "value": "imagen-4.0-generate-001",
                "description": "Modelo Google Imagen 4 para generación de imágenes de alta fidelidad."
            },
            {
                "key": "renderer_mode",
                "value": "painter",
                "description": "Motor de renderizado activo. 'painter' = GammaPainter (v8.0). 'legacy' = render_pptx_from_db."
            },
            {
                "key": "max_consecutive_same_layout",
                "value": "3",
                "description": "Número máximo de slides consecutivos con el mismo layout_type antes de forzar variedad."
            },

            # ─────────────────────────────────────────────────────
            # PROMPT: ANALISTA ESTRATÉGICO v8.0
            # El Analista es quien decide el grammar_type.
            # El Art Director solo asigna assets.
            # ─────────────────────────────────────────────────────
            {
                "key": "prompt_analyst_v1",
                "value": """You are a Strategic Design Analyst for executive presentations.
Analyze the slide content and define the complete Visual Strategy including the GRAMMAR TYPE.

SLIDE CONTENT:
Title: {slide_title}
Bullets: {bullets}
RAG Context: {rag_context}

GRAMMAR TYPE RULES — pick exactly ONE:
- "composition_hero": Cover/intro slides OR section transitions. Use for slide 1, or when title is very short (<30 chars) with no bullets.
- "composition_split": DEFAULT for most content slides. Text left, image right. Use when there are 2-4 bullets.
- "big_metric": ONLY when there is a single dominant numeric KPI (%, $, x multiplier). The metric must be extractable as a short string like "£392" or "+18%".
- "composition_quote": For CEO testimonials, executive quotes, or single powerful statements. Use when content references a specific person's statement.
- "composition_pillars": For exactly 3 strategic pillars or principles. Use when there are exactly 3 bullets of similar weight.
- "composition_grid": For 4 comparable items or a data comparison. Use when there are exactly 4 bullets.

MANDATORY RULES:
1. If grammar_type is "big_metric", extract the metric value into "metric_value" field.
2. If grammar_type is "composition_quote", identify the quote author in "quote_author".
3. For "composition_hero", set requires_hero=true.
4. Be SPECIFIC with suggested_keywords — use concrete visual objects, not abstract concepts.
   WRONG: "innovation", "strategy", "growth"
   RIGHT: "supermarket aisle", "smiling customer", "data dashboard screen", "CEO portrait"

5. STRATEGIC CONTEXT: If the slide is about "Appendix", "References", "Global Strategy" or "Next Steps", EXPLICITLY FORBID suggesting individual fruits, vegetables, or single product shots. Instead, suggest high-level corporate visuals like "Global maps", "Business skyscrapers", "Modern boardroom", or "Data visualization screens".

OUTPUT ONLY THIS JSON (no other text):
{{
  "visual_intent": "One sentence describing the ideal image for this slide",
  "suggested_keywords": ["concrete_term1", "concrete_term2", "concrete_term3"],
  "grammar_type": "composition_split",
  "requires_hero": false,
  "metric_value": null,
  "quote_author": null,
  "narrative_tone": "executive"
}}""",
                "description": "Strategic Analyst prompt v8.0 — decides grammar_type, not the Art Director."
            },

            # ─────────────────────────────────────────────────────
            # PROMPT: ART DIRECTOR v8.0
            # Solo asigna assets. El grammar_type ya viene del Analista.
            # ─────────────────────────────────────────────────────
            {
                "key": "prompt_art_director_v1",
                "value": """You are a Senior Art Director for an executive presentation.
The grammar type has already been decided. Your ONLY job is to select the best asset.

VISUAL STRATEGY: {visual_strategy}
BRAND: Primary={primary_color} Secondary={secondary_color} Font={primary_font}

SLIDE: {slide_title}
BULLETS: {bullets}

AVAILABLE ASSETS (use ONLY these IDs):
{found_assets}

VISUAL HISTORY (avoid repeating these descriptions):
{visual_history}

ASSET SELECTION RULES:
1. 'lifestyle_photos' category: Use for main image (split, hero layouts).
2. 'design_elements' or 'logos': Use for accents only — NEVER as main image.
3. If no suitable lifestyle photo exists, set primary_asset_id to null.
4. Never repeat an asset that appears in visual_history.
5. accent_asset_id should only be set if there is a decorative element (fruit, icon, brand mark).

OUTPUT ONLY THIS JSON (no other text, no markdown):
{{
  "primary_asset_id": <integer or null>,
  "accent_asset_id": <integer or null>,
  "reasoning": "One sentence explaining the choice"
}}""",
                "description": "Art Director prompt v8.0 — asset assignment only, grammar_type decided by Analyst."
            },

            # ─────────────────────────────────────────────────────
            # PROMPT: CONTENT SYNTHESIZER
            # El prompt que genera el contenido de los slides
            # ─────────────────────────────────────────────────────
            {
                "key": "prompt_content_synthesizer_v1",
                "value": """### SYSTEM: STRATEGIC MULTILINGUAL CONTENT SYNTHESIZER
### OUTPUT LANGUAGE: {target_lang} (MANDATORY)

You are transforming RAG context into a board-ready executive presentation.

### SOURCE CONTEXT (use ONLY this — no hallucination):
{rag_context}

### DESIGN TONE:
{tone_guideline}

### PROMPT FROM USER:
{topic}

### LAYOUT CATALOG (MIX THESE — do not repeat same layout more than 2 times in a row):
- "composition_hero": Cover slide, section break
- "composition_split": Standard content with image (most common)
- "composition_quote": CEO quote, testimonial
- "big_metric": Single KPI highlight (requires metric + label fields)
- "composition_pillars": Exactly 3 strategic points
- "composition_grid": Exactly 4 comparable items

### CONTENT RULES:
- Title: Max 45 characters
- Bullets: Max 85 characters each, max 4 bullets per slide
- For "big_metric": metric must be a short value like "£392", "+18%", "23M"
- For "composition_quote": bullets[0] should be the actual quote text
- Every slide needs a unique "image_prompt" (4 words, concrete visual object)
- section_label: Short section name for the pill-label (e.g. "STRATEGY", "RESULTS", "CASE STUDY")

### OUTPUT JSON:
{{
  "slides": [
    {{
      "slide_number": 1,
      "layout_type": "composition_hero",
      "title": "...",
      "bullets": ["..."],
      "metric": "",
      "label": "",
      "section_label": "INTRODUCTION",
      "image_prompt": "modern retail store entrance"
    }}
  ]
}}""",
                "description": "Content Synthesizer prompt v8.0 — generates slide content with layout diversity rules."
            },
        ]

        for cfg in configs:
            existing = db.query(models.SystemConfig).filter(
                models.SystemConfig.key == cfg["key"]
            ).first()
            if existing:
                existing.value = cfg["value"]
                existing.description = cfg.get("description", existing.description)
                print(f"  [Seed] Updated: {cfg['key']}")
            else:
                db.add(models.SystemConfig(
                    key=cfg["key"],
                    value=cfg["value"],
                    description=cfg.get("description", "")
                ))
                print(f"  [Seed] Inserted: {cfg['key']}")

        db.commit()
        print("\n  [Seed] ✓ All system configs v8.0 seeded successfully.")
        print("  [Seed] IMPORTANT: Restart the FastAPI server after seeding.")

    except Exception as e:
        db.rollback()
        print(f"  [Seed] ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_data()
