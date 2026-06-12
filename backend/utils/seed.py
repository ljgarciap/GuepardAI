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
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
                "key": "qa_fidelity_threshold",
                "value": "0.8",
                "description": "Umbral del QA Judge LLM: score < threshold => rework (spec qa-judge-verdict-consistency)."
            },
            {
                "key": "embedding_model_chain",
                "value": "mistral-embed,models/gemini-embedding-2,ollama/mxbai-embed-large",
                "description": "Cadena de modelos para embeddings (v41.0)"
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
            {
                "key": "extraction_vision_model",
                "value": "pixtral-12b-2409,gemini-flash-latest,claude-3-5-sonnet-20241022",
                "description": "Modelo principal para análisis de visión (DNA/Assets)."
            },
            {
                "key": "extraction_synthesis_model",
                "value": "mistral/mistral-large-latest,gemini-flash-latest,claude-3-5-sonnet-20241022",
                "description": "Modelo para síntesis de contenido y estructuración."
            },
            {
                "key": "global_fallback_model",
                "value": "mistral/mistral-large-latest,gemini-flash-latest,claude-3-5-sonnet-20241022",
                "description": "Modelo de respaldo global en caso de fallo de proveedores primarios."
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
            {
                "key": "prompt_analyst_v2",
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

CRITICAL INSTRUCTIONS FOR "visual_intent" AND "suggested_keywords":
1. STRICT NO-TEXT & NO-GRAPHIC RULE: The "visual_intent" description MUST describe a high-end, metaphorical, realistic corporate lifestyle photograph or symbolic object. It MUST NOT describe any charts, diagrams, graphs, tables, dashboards, screens, mockups, or user interfaces.
2. METAPHORICAL REPRESENTATION OF DATA: If the slide contains metrics, financial data, or statistics, DO NOT ask for a drawing of a chart or graphic. Instead, represent it using a real-world metaphor (e.g. "a modern suspension bridge built of concrete and steel", "a lush green plant sprout growing in soil on a clean corporate desk with natural lighting", "a close-up of a neat gears assembly inside a watch", "modern business colleagues collaborating in a brightly lit glass meeting room").
3. NO FORBIDDEN WORDS: Do NOT include words like "chart", "diagram", "graph", "infographic", "table", "metric", "dashboard", "screen", "analytics", "numbers", "letters", "words", "logo", "text" in the "visual_intent" or "suggested_keywords".

OUTPUT JSON:
{{
  "visual_intent": "...",
  "suggested_keywords": ["..."],
  "grammar_type": "...",
  "metric_value": null
}}""",
                "description": "Strategic Analyst v8.7 — Metaphorical prompt styling with strict no-text and no-graphic constraints."
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

# BRAND VISION DNA (Extracted by Visual Analyst):
{vision_dna_json}

# PREMIUM PATTERNS (Available for use):
{premium_patterns_json}

# STRATEGIC CONTEXT:
- Visual Strategy: {visual_strategy}
- Slide Title: {slide_title}
- Content: {bullets}

# AVAILABLE BRAND ASSETS (From Official Library):
{found_assets}

# VISUAL HISTORY (DO NOT REPEAT):
{visual_history}

# REPLIT-GRADE DESIGN INSTRUCTIONS (Designer Mode v5.0):
1. PHOTOGRAPHY FIRST: For 'composition_split' and 'composition_hero', you MUST prioritize 'lifestyle_photos'. AVOID using a single 'design_element' to fill these layouts.
2. DESIGN ELEMENTS AS ACCENTS: Use 'design_elements' ONLY for typographic substitution, small accents, or in 'custom_canvas'. NEVER scale them to fill more than 20% of the slide.
3. QUALITY GUARD: NEVER select assets categorized as 'noise'.
4. REASONING: Justify why the chosen photo or element enhances the strategic narrative.
5. VARIETY ENFORCEMENT: Review the VISUAL HISTORY. If the previous slides used 'split' or 'full_bleed', you MUST choose a different layout ('pillars', 'data_grid', 'custom_canvas'). DO NOT repeat layouts consecutively.
6. COLLISION SAFE-ZONE: The Title and Subtitle occupy the top zone (y=0 to y=25). NEVER place canvas_elements above y=25. Elements placed in this restricted zone will overlap the title and ruin the design.

# OUTPUT FORMAT (STRICT JSON):
{{
  "primary_asset_id": <int or null>,
  "accent_asset_id": <int or null>,
  "visual_reasoning": "Explain the design-led choice.",
  "suggested_layout_override": "hero | data_grid | pillars | split | custom_canvas",
  "canvas_elements": [
    {{{{ "type": "typo_substitution", "text": "Loyalty", "char": "a", "path": "asset_basename", "x": 10, "y": 40, "size": 90 }}}},
    {{{{ "type": "image", "path": "person_photo", "x": 60, "y": 30, "w": 40, "h": 80 }}}},
    {{{{ "type": "text", "content": "Data to Growth", "x": 10, "y": 55, "size": 24, "color": "#FFFFFF" }}}}
  ]
}}
""",
                "description": "Art Director v5.0 — Replit-Grade Reasoning & Creative Curation."
            },
            {
                # v2 = v1 + conciencia de perfil visual (el seeder no hace upsert de claves existentes)
                "key": "prompt_art_director_v2",
                "value": """# ROLE: Senior Executive Art Director
You are responsible for the VISUAL FIDELITY and BRAND ADHERENCE of a high-stakes presentation.

# BRAND ARTISTIC ESSENCE (READ CAREFULLY):
{art_direction_note}

# BRAND VISION DNA (Extracted by Visual Analyst):
{vision_dna_json}

# PREMIUM PATTERNS (Available for use):
{premium_patterns_json}

# STRATEGIC CONTEXT:
- Visual Strategy: {visual_strategy}
- Slide Title: {slide_title}
- Content: {bullets}

# AVAILABLE BRAND ASSETS (From Official Library):
{found_assets}

# VISUAL HISTORY (DO NOT REPEAT):
{visual_history}

# REPLIT-GRADE DESIGN INSTRUCTIONS (Designer Mode v5.1):
1. PHOTOGRAPHY FIRST: For 'composition_split' and 'composition_hero', you MUST prioritize 'lifestyle_photos'. AVOID using a single 'design_element' to fill these layouts.
2. DESIGN ELEMENTS AS ACCENTS: Use 'design_elements' ONLY for typographic substitution, small accents, or in 'custom_canvas'. NEVER scale them to fill more than 20% of the slide.
3. QUALITY GUARD: NEVER select assets categorized as 'noise'.
4. REASONING: Justify why the chosen photo or element enhances the strategic narrative.
5. VARIETY ENFORCEMENT: Review the VISUAL HISTORY. If the previous slides used 'split' or 'full_bleed', you MUST choose a different layout ('pillars', 'data_grid', 'custom_canvas'). DO NOT repeat layouts consecutively.
6. COLLISION SAFE-ZONE: The Title and Subtitle occupy the top zone (y=0 to y=25). NEVER place canvas_elements above y=25. Elements placed in this restricted zone will overlap the title and ruin the design.
7. VISUAL PROFILE AWARENESS: Some assets include a 'visual_profile' (orientation, subject_position, negative_space, layout_suitability). STRONGLY PREFER assets whose 'negative_space' zones overlap the layout's text area and whose 'layout_suitability' includes the role of the target layout (hero, split, accent...). NEVER place text over the subject: if 'subject_position' is 'left', text belongs on the right, and vice versa.

# OUTPUT FORMAT (STRICT JSON):
{{
  "primary_asset_id": <int or null>,
  "accent_asset_id": <int or null>,
  "visual_reasoning": "Explain the design-led choice.",
  "suggested_layout_override": "hero | data_grid | pillars | split | custom_canvas",
  "canvas_elements": [
    {{{{ "type": "typo_substitution", "text": "Loyalty", "char": "a", "path": "asset_basename", "x": 10, "y": 40, "size": 90 }}}},
    {{{{ "type": "image", "path": "person_photo", "x": 60, "y": 30, "w": 40, "h": 80 }}}},
    {{{{ "type": "text", "content": "Data to Growth", "x": 10, "y": 55, "size": 24, "color": "#FFFFFF" }}}}
  ]
}}
""",
                "description": "Art Director v5.1 — Visual Profile Awareness (negative space, subject position, layout suitability)."
            },
            {
                "key": "prompt_classifier_v1",
                "value": """# ROLE: Expert Visual Asset Analyst & Art Director
Analyze this image with TECHNICAL DESIGN RIGOR and return a JSON with:
- 'category': Choose one: 
    * 'lifestyle_photos': Complex scenes, people, stores, or environments.
    * 'design_elements': Single isolated objects (fruits, products), icons, or accents on solid/transparent backgrounds. 
    * 'logos': Brand identities, company names, or wordmarks. (CRITICAL: If it is a brand logo, it MUST be 'logos' regardless of transparency or isolation).
    * 'backgrounds': Textures or full-page backgrounds.
    * 'noise': Blank, blurry, low-quality, or useless images.
- 'is_person': boolean.
- 'background_type': 'transparent', 'solid_white', 'solid_black', 'complex', or 'other'.
- 'description': TECHNICAL INSTRUCTION: Provide a VISUAL and COMPOSITIONAL description (Max 3 sentences). Focus strictly on the Subject, Composition (e.g., 'Centered', 'Negative space on left'), Dominant Colors, and Design Potential (e.g., 'Suitable for typographic substitution'). AVOID corporate fluff like 'strategic value', 'approachable' or 'professional'.
- 'tags': 5 technical keywords for designer search.""",
                "description": "Asset Classifier v3.0 — Technical Designer Focus (Replit-Grade)."
            },
            {
                # NOTA: el seeder OMITE claves existentes (no hace upsert), por eso
                # los cambios de prompt van en una clave nueva versionada (_v2).
                "key": "prompt_classifier_v2",
                "value": """# ROLE: Expert Visual Asset Analyst & Art Director
Analyze this image with TECHNICAL DESIGN RIGOR and return a JSON with:
- 'category': Choose one:
    * 'lifestyle_photos': Complex scenes, people, stores, or environments.
    * 'design_elements': Single isolated objects (fruits, products), icons, or accents on solid/transparent backgrounds.
    * 'logos': Brand identities, company names, or wordmarks. (CRITICAL: If it is a brand logo, it MUST be 'logos' regardless of transparency or isolation).
    * 'backgrounds': Textures or full-page backgrounds.
    * 'noise': Blank, blurry, low-quality, or useless images.
- 'is_person': boolean.
- 'background_type': 'transparent', 'solid_white', 'solid_black', 'complex', or 'other'.
- 'description': TECHNICAL INSTRUCTION: Provide a VISUAL and COMPOSITIONAL description (Max 3 sentences). Focus strictly on the Subject, Composition (e.g., 'Centered', 'Negative space on left'), Dominant Colors, and Design Potential (e.g., 'Suitable for typographic substitution'). AVOID corporate fluff like 'strategic value', 'approachable' or 'professional'.
- 'tags': 5 technical keywords for designer search.
- 'orientation': 'landscape', 'portrait', or 'square' (based on the image proportions).
- 'dominant_colors': List of up to 4 hex colors (e.g. ["#1A73E8", "#FFFFFF"]), ordered by visual weight.
- 'composition': Object with:
    * 'subject_position': 'left', 'center', 'right', or 'full' (where the main subject sits).
    * 'negative_space': List of zones with clean/empty space usable for text overlay: 'top', 'bottom', 'left', 'right', 'center', or 'none'.
- 'layout_suitability': List of slide layout roles this image works well for. Choose from:
    * 'hero': Strong full-bleed background; subject tolerates text overlay or sits off-center.
    * 'split': Works cropped into a half-slide vertical panel.
    * 'accent': Small decorative or supporting placement only.
    * 'background': Texture/pattern suitable as a subtle backdrop.
    * 'data_grid': Clean enough to sit behind or beside data cards.
    * 'pillars': Crops well into narrow vertical columns.""",
                "description": "Asset Classifier v4.0 — Visual Profile (orientation, colors, composition, layout suitability)."
            },
            {
                "key": "aspect_ratio_tolerance",
                "value": "0.40",
                "description": "Tolerancia relativa de diferencia de aspect ratio imagen vs panel del layout (Fase B Art Director)."
            },
            {
                "key": "degraded_min_resolution_px",
                "value": "600",
                "description": "Piso duro de ancho (px) para re-admitir assets en la degradación de la Fase B en layouts NO hi-res (Calidad Selección v2). Hi-res nunca degrada por debajo de 1200px."
            },
            {
                "key": "qa_feedback_max_chars",
                "value": "1500",
                "description": "Máximo de caracteres del feedback de QA inyectado en el prompt del Art Director en los retries (F1 fixes-resiliencia)."
            },
            {
                "key": "auto_data_alignment_enabled",
                "value": "true",
                "description": "Si es 'true', el arranque encola automáticamente las alineaciones de datos pendientes (pueden consumir tokens LLM)."
            },
            {
                "key": "is_footer_enabled",
                "value": "true",
                "description": "Determina si el footer/firma está habilitado de forma global."
            }
        ]

        for cfg in configs:
            existing = db.query(models.SystemConfig).filter(
                models.SystemConfig.key == cfg["key"]
            ).first()
            if existing:
                print(f"  [Seed] Skipped (already exists): {cfg['key']}")
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
            {"code": "UK", "name": "English (UK)", "priority": 1},
            {"code": "USA", "name": "English (USA)", "priority": 2},
            {"code": "FR", "name": "French", "priority": 3},
            {"code": "LATAM", "name": "Spanish (LATAM)", "priority": 4},
            {"code": "ES", "name": "Spanish (Spain)", "priority": 5}
        ]

        for lang in languages:
            existing_lang = db.query(models.Language).filter(
                models.Language.code == lang["code"]
            ).first()
            if not existing_lang:
                db.add(models.Language(**lang))
                print(f"  [Seed] Inserted Language: {lang['name']}")
            else:
                print(f"  [Seed] Skipped Language (already exists): {lang['name']}")

        # ─────────────────────────────────────────────────────
        # SURVEY QUESTIONS (SISTEMA DE CALIFICACIÓN PARAMÉTRICO)
        # ─────────────────────────────────────────────────────
        questions = [
            {
                "key": "presentation_satisfaction",
                "question_text": "How satisfied are you with the generated presentation?",
                "question_type": "stars",
                "is_active": True
            }
        ]

        for q in questions:
            existing_q = db.query(models.SurveyQuestion).filter(
                models.SurveyQuestion.key == q["key"]
            ).first()
            if not existing_q:
                db.add(models.SurveyQuestion(**q))
                print(f"  [Seed] Inserted Survey Question: {q['key']}")
            else:
                print(f"  [Seed] Skipped Survey Question (already exists): {q['key']}")

        # ─────────────────────────────────────────────────────
        # DEFAULT FOOTER CONFIGURATIONS
        # ─────────────────────────────────────────────────────
        default_footers = [
            {
                "name": "Default Founders of Loyalty & Tesco Footer",
                "text": "L - founders of loyalty",
                "disclaimer": "CONFIDENTIAL FOR {brand} USE ONLY",
                "is_active": True,
                "is_selected": True
            }
        ]

        for f in default_footers:
            existing_f = db.query(models.FooterConfig).filter(
                models.FooterConfig.name == f["name"]
            ).first()
            if not existing_f:
                db.add(models.FooterConfig(**f))
                print(f"  [Seed] Inserted Default Footer Config: {f['name']}")
            else:
                existing_f.text = f["text"]
                existing_f.disclaimer = f["disclaimer"]
                existing_f.is_active = f["is_active"]
                existing_f.is_selected = f["is_selected"]
                print(f"  [Seed] Updated Default Footer Config (applied new text & disclaimer): {f['name']}")

        db.commit()
        print("\n  [Seed] ✓ All system configs, languages, survey questions, and footers seeded successfully.")

    except Exception as e:
        db.rollback()
        print(f"  [Seed] ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_data()
