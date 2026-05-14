"""
seed.py — GuepardAI v8.5
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CAMBIOS v8.5:
  - Meta-Prompting: Prompt Architect + Content Synthesizer v2
  - Audience-Centric Hero Layout support
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
                "key": "agency_name",
                "value": "L - Founders of Loyalty",
                "description": "Nombre de la empresa que genera la presentación (Branding de Autor)."
            },
            {
                "key": "agency_logo_path",
                "value": "assets/agency/L-founders_logo.png",
                "description": "Ruta al logo de la agencia para el footer/firma."
            },
            {
                "key": "asset_score_threshold",
                "value": "0.45",
                "description": "Umbral mínimo de similitud semántica para aceptar asset."
            },
            {
                "key": "embedding_model_chain",
                "value": "mistral-embed,models/gemini-embedding-2",
                "description": "Cadena de modelos de embedding."
            },
            {
                "key": "model_image_gen",
                "value": "imagen-4.0-generate-001",
                "description": "Modelo Google Imagen 4."
            },
            {
                "key": "renderer_mode",
                "value": "painter",
                "description": "Motor de renderizado activo."
            },
            {
                "key": "max_consecutive_same_layout",
                "value": "3",
                "description": "Número máximo de slides consecutivos con el mismo layout_type."
            },
            
            # ─────────────────────────────────────────────────────
            # PROMPT: ANALISTA ESTRATÉGICO v8.5
            # ─────────────────────────────────────────────────────
            {
                "key": "prompt_analyst_v1",
                "value": """You are a Strategic Design Analyst for executive presentations.
Analyze the slide content and define the Visual Strategy.

SLIDE CONTENT:
Title: {slide_title}
Bullets: {bullets}
RAG Context: {rag_context}

GRAMMAR TYPE RULES:
- "composition_hero": Cover or Section Breaks.
- "composition_split": Content with supporting image.
- "big_metric": Single major KPI hero.
- "composition_quote": Testimonials or strategic pillars.
- "data_grid_cards": Dashboards (3-6 metrics).
- "composition_pillars": 3-4 distinct columns.

OUTPUT JSON:
{{
  "visual_intent": "...",
  "suggested_keywords": ["..."],
  "grammar_type": "...",
  "metric_value": null
}}""",
                "description": "Strategic Analyst v8.6."
            },

            # ─────────────────────────────────────────────────────
            # PROMPT: ART DIRECTOR v8.0
            # ─────────────────────────────────────────────────────
            {
                "key": "prompt_art_director_v1",
                "value": """You are a Senior Art Director. Select the best asset.
VISUAL STRATEGY: {visual_strategy}
BRAND: {primary_color}, {secondary_color}
SLIDE: {slide_title}
AVAILABLE ASSETS: {found_assets}

OUTPUT ONLY THIS JSON:
{{
  "primary_asset_id": <int>,
  "reasoning": "..."
}}""",
                "description": "Art Director prompt v8.0."
            },

            # ─────────────────────────────────────────────────────
            # PROMPT: PROMPT ARCHITECT v1.2
            # ─────────────────────────────────────────────────────
            {
                "key": "prompt_architect_v1",
                "value": """### ROLE: ELITE PROMPT ENGINEER & STRATEGIC ARCHITECT
### TASK: Transform the USER PROMPT into a HYPER-SPECIFIC, high-fidelity MASTER INSTRUCTION.

### CRITICAL RULES:
1. NO SUMMARIZING: Do NOT condense the user's specific requests. If they ask for "Global case studies" and "CEO testimonials", those exact phrases and their context MUST be in the master instruction.
2. NARRATIVE AMPLIFICATION: Expand the user's intent into a 20-slide narrative flow.
3. BRAND & TONE LOYALTY: Force the synthesizer to use the specific corporate tone of {brand_name}.
4. DATA HUNGER: Explicitly instruct the synthesizer to DIG into the RAG context for names, dates, and figures.

### MASTER INSTRUCTION STRUCTURE (OUTPUT ONLY THIS JSON):
{{
  "polished_instruction": "You are a Senior Strategic Lead for {brand_name}. YOUR MISSION: {topic}. \n\nAMPLIFICATION GUIDELINES:\n- PRESERVE: Do NOT summarize the mission. Keep all specific names and requirements.\n- DEPTH: Generate exactly 15-20 slides.\n- CASE STUDIES: You MUST include real retailer names and KPIs from the context.\n- TONE: {tone_guideline}.\n- METADATA: Populate 'prepared_for' with the recipient's name from the prompt.",
  "strategic_rationale": "Amplified for maximum strategic depth and compliance with specific user mandates."
}}""",
                "description": "Prompt Architect v1.2 — Aggressive compliance and depth."
            },

            # ─────────────────────────────────────────────────────
            # PROMPT: CONTENT SYNTHESIZER v2.1
            # ─────────────────────────────────────────────────────
            {
                "key": "prompt_content_synthesizer_v2",
                "value": """### MASTER INSTRUCTION:
{polished_prompt}

### ADDITIONAL CONTEXT (RAG):
{rag_context}

### OUTPUT SPECIFICATIONS:
- Output Language: {target_lang}
- Max Slides: 20
- **Slide 1 (COVER)**: MUST have 'metadata' with 'prepared_for', 'confidential' (boolean), and 'date'.
- **Layout Types**: [composition_hero, composition_split, composition_quote, data_grid_cards, composition_pillars]

### MANDATORY JSON FORMAT:
{{
  "slides": [
    {{
      "title": "...",
      "subtitle": "Strategic Subtitle",
      "layout_type": "composition_pillars",
      "section_label": "...",
      "bullets": ["Point 1 with data", "Point 2 with detail", "Point 3 with outcome"],
      "metrics": [ {{"label": "KPI", "value": "X%", "growth": "+Y%"}} ],
      "metadata": {{ "prepared_for": "...", "confidential": true, "date": "..." }}
    }}
  ]
}}""",
                "description": "Content Synthesizer v2.1 — Strategic depth and RAG extraction."
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
        print("\n  [Seed] ✓ All system configs v8.5 seeded successfully.")

    except Exception as e:
        db.rollback()
        print(f"  [Seed] ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_data()
