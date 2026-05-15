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
                "key": "agency_contact_email",
                "value": "partners@l-founders.com",
                "description": "Email de contacto para el cierre de presentaciones."
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
            {
                "key": "prompt_art_director_v1",
                "value": """# ROLE: Senior Executive Art Director
You are responsible for the VISUAL FIDELITY and BRAND ADHERENCE of a high-stakes presentation.

# BRAND ARTISTIC ESSENCE (READ CAREFULLY):
{art_direction_note}

# STRATEGIC CONTEXT:
- Visual Strategy: {visual_strategy}
- Slide Title: {slide_title}
- Content: {bullets}

# AVAILABLE BRAND ASSETS (From Official Library):
{found_assets}

# REPLIT-GRADE DESIGN INSTRUCTIONS (Designer Mode v4.0):
1. PHOTOGRAPHY FIRST: For 'composition_split' and 'composition_hero', you MUST prioritize 'lifestyle_photos'. AVOID using a single 'design_element' to fill these layouts.
2. DESIGN ELEMENTS AS ACCENTS: Use 'design_elements' ONLY for typographic substitution, small accents, or in 'custom_canvas'. NEVER scale them to fill more than 20% of the slide.
3. QUALITY GUARD: NEVER select assets categorized as 'noise'.
4. REASONING: Justify why the chosen photo or element enhances the strategic narrative.

# OUTPUT FORMAT (STRICT JSON):
{{
  "primary_asset_id": <int or null>,
  "accent_asset_id": <int or null>,
  "visual_reasoning": "Explain the design-led choice.",
  "suggested_layout_override": "hero | data_grid | pillars | split | custom_canvas",
  "canvas_elements": [
    {{{{ "type": "typo_substitution", "text": "Loyalty", "char": "a", "path": "asset_basename", "x": 10, "y": 40, "size": 90 }}}},
    {{{{ "type": "image", "path": "person_photo", "x": 60, "y": 10, "w": 40, "h": 80 }}}},
    {{{{ "type": "text", "content": "Data to Growth", "x": 10, "y": 55, "size": 24, "color": "#FFFFFF" }}}}
  ]
}}
""",
                "description": "Art Director v2.0 — Replit-Grade Reasoning & Creative Curation."
            },
            {
                "key": "prompt_classifier_v1",
                "value": """# ROLE: Expert Visual Asset Analyst & Art Director
Analyze this image with TECHNICAL DESIGN RIGOR and return a JSON with:
- 'category': Choose one: 
    * 'lifestyle_photos': Complex scenes, people, stores, or environments.
    * 'design_elements': Single isolated objects (fruits, products), icons, or accents on solid/transparent backgrounds. (CRITICAL: If it's a fruit or object, it's a 'design_element').
    * 'logos': Brand identities.
    * 'backgrounds': Textures or full-page backgrounds.
    * 'noise': Blank, blurry, low-quality, or useless images.
- 'is_person': boolean.
- 'background_type': 'transparent', 'solid_white', 'solid_black', 'complex', or 'other'.
- 'description': TECHNICAL INSTRUCTION: Provide a VISUAL and COMPOSITIONAL description (Max 3 sentences). Focus strictly on the Subject, Composition (e.g., 'Centered', 'Negative space on left'), Dominant Colors, and Design Potential (e.g., 'Suitable for typographic substitution'). AVOID corporate fluff like 'strategic value', 'approachable' or 'professional'.
- 'tags': 5 technical keywords for designer search.
""",
                "description": "Asset Classifier v3.0 — Technical Designer Focus (Replit-Grade)."
            }
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

        # ─────────────────────────────────────────────────────
        # IDIOMAS BASE
        # ─────────────────────────────────────────────────────
        languages = [
            {"code": "LATAM", "name": "Español (LATAM)", "priority": 1},
            {"code": "UK", "name": "English (UK)", "priority": 2},
            {"code": "USA", "name": "English (USA)", "priority": 3},
            {"code": "ES", "name": "Español (España)", "priority": 4}
        ]

        for lang in languages:
            existing_lang = db.query(models.Language).filter(
                models.Language.code == lang["code"]
            ).first()
            if not existing_lang:
                db.add(models.Language(**lang))
                print(f"  [Seed] Inserted Language: {lang['name']}")

        db.commit()
        print("\n  [Seed] ✓ All system configs and languages v8.5 seeded successfully.")

    except Exception as e:
        db.rollback()
        print(f"  [Seed] ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_data()
