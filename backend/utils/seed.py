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


CONFIGS = [

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
                # v3 = v2 + explicit plain-text enforcement (no markdown in any text field)
                # Seeder skips existing keys — deployed DBs pick this up on next restart.
                "key": "prompt_content_synthesizer_v3",
                "value": """### MASTER INSTRUCTION:
{polished_prompt}

### ADDITIONAL CONTEXT (RAG):
{rag_context}

### OUTPUT SPECIFICATIONS:
- Output Language: {target_lang}
- Max Slides: 20
- **Slide 1 (COVER)**: MUST have 'metadata' with 'prepared_for', 'confidential' (boolean), and 'date'.
- **Layout Types**: [composition_hero, composition_split, composition_quote, data_grid_cards, composition_pillars]

### CRITICAL PLAIN-TEXT RULE:
ALL text in title, subtitle, bullets, and metric labels MUST be plain text.
DO NOT use any Markdown formatting: no **, no *, no _, no #, no backticks, no [text](url).
The rendering engine does not support Markdown — any formatting markers will appear as literal characters.

### MANDATORY JSON FORMAT:
{{
  "slides": [
    {{
      "title": "Plain text title without asterisks",
      "subtitle": "Plain text subtitle",
      "layout_type": "composition_pillars",
      "section_label": "STRATEGY",
      "bullets": ["Plain text point with data", "Plain text point with detail", "Plain text point with outcome"],
      "metrics": [ {{"label": "KPI Label", "value": "X%", "growth": "+Y%"}} ],
      "metadata": {{ "prepared_for": "...", "confidential": true, "date": "..." }}
    }}
  ]
}}""",
                "description": "Content Synthesizer v3.0 — Strict plain-text enforcement (no Markdown)."
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
                # v3 = v2 + correct layout slug vocabulary (hero/split/pillars/data_grid/custom_canvas)
                # Seeder skips existing keys — deployed DBs pick this up on next restart.
                "key": "prompt_analyst_v3",
                "value": """You are a Strategic Design Analyst for executive presentations.
Analyze the slide content and define the Visual Strategy.

SLIDE CONTENT:
Title: {slide_title}
Bullets: {bullets}
RAG Context: {rag_context}

GRAMMAR TYPE RULES (use EXACTLY these values):
- "hero": Cover slides or Section Breaks. Full-screen image with title overlay.
- "split": Content with supporting image. Image on one side, text on the other.
- "data_grid": Quantitative data, KPIs, or dashboards (3-6 metrics).
- "pillars": 3-4 distinct columns or strategic pillars.
- "custom_canvas": Full creative freedom. Complex or mixed layouts.

CRITICAL INSTRUCTIONS FOR "visual_intent" AND "suggested_keywords":
1. STRICT NO-TEXT & NO-GRAPHIC RULE: The "visual_intent" description MUST describe a high-end, metaphorical, realistic corporate lifestyle photograph or symbolic object. It MUST NOT describe any charts, diagrams, graphs, tables, dashboards, screens, mockups, or user interfaces.
2. METAPHORICAL REPRESENTATION OF DATA: If the slide contains metrics, financial data, or statistics, DO NOT ask for a drawing of a chart or graphic. Instead, represent it using a real-world metaphor (e.g. "a modern suspension bridge built of concrete and steel", "a lush green plant sprout growing in soil on a clean corporate desk with natural lighting").
3. NO FORBIDDEN WORDS: Do NOT include words like "chart", "diagram", "graph", "infographic", "table", "metric", "dashboard", "screen", "analytics", "numbers", "letters", "words", "logo", "text" in the "visual_intent" or "suggested_keywords".

OUTPUT JSON:
{{
  "visual_intent": "...",
  "suggested_keywords": ["..."],
  "grammar_type": "...",
  "metric_value": null
}}""",
                "description": "Strategic Analyst v8.8 — Corrected layout slug vocabulary (hero/split/pillars/data_grid/custom_canvas)."
            },
            {
                # v3 = v2 + corrected photography instruction slugs (hero/split instead of composition_hero/composition_split)
                # Seeder skips existing keys — deployed DBs pick this up on next restart.
                "key": "prompt_art_director_v3",
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

# REPLIT-GRADE DESIGN INSTRUCTIONS (Designer Mode v5.2):
1. PHOTOGRAPHY FIRST: For 'split' and 'hero' layouts, you MUST prioritize 'lifestyle_photos'. AVOID using a single 'design_element' to fill these layouts.
2. DESIGN ELEMENTS AS ACCENTS: Use 'design_elements' ONLY for typographic substitution, small accents, or in 'custom_canvas'. NEVER scale them to fill more than 20% of the slide.
3. QUALITY GUARD: NEVER select assets categorized as 'noise'.
4. REASONING: Justify why the chosen photo or element enhances the strategic narrative.
5. VARIETY ENFORCEMENT: Review the VISUAL HISTORY. If the previous slides used 'split' or 'hero', you MUST choose a different layout ('pillars', 'data_grid', 'custom_canvas'). DO NOT repeat layouts consecutively.
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
                "description": "Art Director v5.2 — Corrected layout slug vocabulary (hero/split instead of composition_hero/composition_split)."
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
            },
            {
                # Option A — 3-step surgical RAG pipeline.
                # Produces slide structure only (titles/sections/layouts); content team fills details.
                # Seeder skips existing keys — deployed DBs pick this up on next restart.
                "key": "prompt_content_outline_v1",
                "value": """### ROLE: STRATEGIC PRESENTATION PLANNER
Your only job is to create a slide-by-slide STRUCTURE. Do NOT write any content, bullets, or metrics.
The content team fills in all details per slide using targeted company data.

### MASTER INSTRUCTION:
{polished_prompt}

### INITIAL CONTEXT (use only to decide structure — do not use as content):
{rag_context}

### REQUIREMENTS:
- Output Language: {target_lang}
- Generate between 15 and 20 slides
- Slide 1 MUST be the COVER (layout_type: composition_hero, section_label: COVER)
- Last slide MUST be a closing/next-steps slide
- Allowed layout_type values: [composition_hero, composition_split, composition_quote, data_grid_cards, composition_pillars]
- Avoid using the same layout_type on two consecutive slides

### OUTPUT — ONLY THIS JSON, nothing else:
{{
  "slides": [
    {{"title": "...", "section_label": "...", "layout_type": "..."}}
  ]
}}""",
                "description": "Content Outline v1.0 — Slide structure only (title/section/layout, no content)."
            },
            {
                "key": "prompt_slide_content_v1",
                "value": """### ROLE: STRATEGIC CONTENT WRITER — SINGLE SLIDE
Write content for exactly ONE slide. Use COMPANY DATA as your primary source.

### SLIDE CONTEXT:
- Title: {slide_title}
- Section: {section_label}
- Layout: {layout_type}
- Brand: {brand_name}
- Language: {target_lang}

### COMPANY DATA (ground every claim here — primary source):
{rag_context}

### RULES:
1. Extract REAL metrics, figures, and dates from COMPANY DATA. If a specific figure is absent, write a strategic insight without inventing numbers.
2. Maximum 4 bullets. Each: one specific insight or proven fact. No intro sentences.
3. For data_grid_cards layout: include 3-4 metrics objects with real values from COMPANY DATA.
4. For COVER section (section_label = COVER): populate metadata and subtitle — bullets can be empty.
5. PLAIN TEXT ONLY — no Markdown: no **, no *, no _, no #, no backticks, no links.
6. visual_intent: describe a corporate lifestyle photograph — NO charts, NO screens, NO text in image.

### OUTPUT — ONLY THIS JSON, nothing else:
{{
  "bullets": ["Plain text insight", "Plain text insight"],
  "subtitle": "Strategic tagline (COVER only, empty string otherwise)",
  "metrics": [{{"label": "KPI Name", "value": "X%", "growth": "+Y%"}}],
  "visual_intent": "Corporate photograph description without charts or screens",
  "visual_tags": ["keyword1", "keyword2", "keyword3"],
  "objective": "One sentence: what this slide achieves in the narrative",
  "metadata": {{"prepared_for": "Client Name", "confidential": true, "date": "Month YYYY"}}
}}""",
                "description": "Slide Content v1.0 — Content for ONE slide given targeted RAG context."
            },
            {
                "key": "content_pipeline_parallel_workers",
                "value": "4",
                "description": "ThreadPoolExecutor workers for parallel per-slide content generation (Option A pipeline)."
            },
            {
                # v2 = v1 + evidence-conditioned amplification — never forces aspirational
                # named slides (CEO quotes, testimonials) without RAG backing.
                # Seeder skips existing keys — deployed DBs pick this up on next restart.
                "key": "prompt_architect_v2",
                "value": """### ROLE: ELITE PROMPT ENGINEER & STRATEGIC ARCHITECT
### TASK: Transform the USER PROMPT into a precise MASTER INSTRUCTION.

### CRITICAL RULES:
1. EVIDENCE-FIRST: Preserve the user's strategic intent but DO NOT mandate specific named
   testimonials, CEO quotes, or case studies unless they are evidenced in the company context.
   Convert aspirational requests to evidence-types:
   "CEO testimonial" → "Customer Success Evidence"
   "Named case study" → "Implementation Results"
2. NARRATIVE STRUCTURE: Expand the user's intent into a 15-20 slide flow.
3. BRAND & TONE LOYALTY: Use the specific corporate tone of {brand_name}.
4. DATA HUNGER: Extract real figures, dates, and programme names from context.
   If data is absent, write strategic principles — no invented numbers.
5. NO BRACKETS: The master instruction MUST NEVER contain [Name], [Company], [Year].
   Use generic descriptors: "a retail CEO", "a leading UK retailer".

### OUTPUT ONLY THIS JSON:
{{
  "polished_instruction": "You are a Senior Strategic Lead for {brand_name}. YOUR MISSION: {topic}.\\n\\nGUIDELINES:\\n- STRUCTURE: Generate exactly 15-20 slides.\\n- DATA: Use only figures and names present in the RAG context. If absent, write strategic principles — no bracket placeholders.\\n- TONE: {tone_guideline}.\\n- NO BRACKETS: Never write [Name], [Company] or [Year] in any field.",
  "strategic_rationale": "Evidence-conditioned amplification for {brand_name}."
}}""",
                "description": "Prompt Architect v2.0 — Evidence-first amplification, no aspirational bracket placeholders."
            },
            {
                # v2 = v1 + title char limit + anti-placeholder rule for aspirational slides.
                "key": "prompt_content_outline_v2",
                "value": """### ROLE: STRATEGIC PRESENTATION PLANNER
Your only job is to create a slide-by-slide STRUCTURE. Do NOT write any content, bullets, or metrics.

### MASTER INSTRUCTION:
{polished_prompt}

### INITIAL CONTEXT (use only to decide structure — do not use as content):
{rag_context}

### REQUIREMENTS:
- Output Language: {target_lang}
- Generate between 15 and 20 slides
- Slide 1 MUST be the COVER (layout_type: composition_hero, section_label: COVER)
- Last slide MUST be a closing/next-steps slide
- Allowed layout_type values: [composition_hero, composition_split, composition_quote, data_grid_cards, composition_pillars]
- Avoid using the same layout_type on two consecutive slides

### CRITICAL CONSTRAINTS:
- Title: MAXIMUM 55 characters. No ellipsis. NEVER use [X] or bracket notation.
- NEVER create slides requiring named entities (CEO name, person name, company name)
  UNLESS that exact name appears in INITIAL CONTEXT.
- If a testimonial or case study is requested but no name exists in context,
  use a generic equivalent: "Customer Success Evidence", "Implementation Results".

### OUTPUT — ONLY THIS JSON, nothing else:
{{
  "slides": [
    {{"title": "...", "section_label": "...", "layout_type": "..."}}
  ]
}}""",
                "description": "Content Outline v2.0 — Anti-placeholder, 55-char title limit, no aspirational named slides."
            },
            {
                # Narrator — post-generation narrative cohesion pass.
                # Runs after all per-slide workers finish, before persist (STEP 4.5).
                # One LLM call over the full deck; corrects subtitle/bullets/objective only.
                # Seeder skips existing keys — deployed DBs pick this up on next restart.
                "key": "prompt_narrator_v1",
                "value": """### ROLE: NARRATIVE COHESION EDITOR
You are reviewing a completed strategic presentation for {brand_name}.
All slides have been drafted. Your ONLY job: identify narrative disconnects and produce
targeted corrections so the deck reads as a coherent whole.

### STRATEGIC FRAME (global intent — do not repeat verbatim):
{strategic_context}

### TARGET LANGUAGE: {target_lang}

### FULL DECK — {slide_count} slides (compact view):
{slides_json}

### WHAT TO LOOK FOR:
1. Section opener slides (layout_type: full_bleed_hero or composition_hero) with an empty
   subtitle that leave the reader with no preview of what follows.
2. Slides whose bullets do not connect logically to the slide title or to the previous
   section opener's promise.
3. A closing slide that does not resolve the narrative arc started at the opener.

### CORRECTION RULES:
- Only correct fields: "subtitle", "bullets", or "objective". NEVER change "title",
  "layout_type", or "section_label".
- Do NOT invent data. Reframe, reorder, or clarify using content already present in the deck.
- Corrections must be in {target_lang}.
- Correct at most 40% of slides. Prioritise the highest-impact gaps.
- For "bullets": new_value must be an array of strings.
- For "subtitle" or "objective": new_value must be a plain string.
- If the deck is already cohesive, return an empty corrections array.

### OUTPUT — valid JSON only, no markdown, no explanation outside the JSON:
{{
  "corrections": [
    {{
      "slide_index": <0-based integer>,
      "field": "subtitle",
      "new_value": "<plain text string>",
      "reason": "<one-line explanation>"
    }}
  ],
  "cohesion_score": <float 0.0-1.0>,
  "gaps_found": ["<description of each gap identified>"]
}}""",
                "description": "Narrator v1.0 — Post-generation narrative cohesion pass (STEP 4.5). Corrects subtitle/bullets/objective only."
            },
            {
                # v2 = v1 + strategic_context slot + stricter anti-placeholder + char limits.
                "key": "prompt_slide_content_v2",
                "value": """### ROLE: STRATEGIC CONTENT WRITER — SINGLE SLIDE
Write content for exactly ONE slide. Use COMPANY DATA as your primary source.

### STRATEGIC FRAME (what this presentation achieves — do not repeat verbatim):
{strategic_context}

### SLIDE CONTEXT:
- Title: {slide_title}
- Section: {section_label}
- Layout: {layout_type}
- Brand: {brand_name}
- Language: {target_lang}

### COMPANY DATA (ground every claim here — primary source):
{rag_context}

### RULES:
1. Extract REAL metrics, figures, and dates from COMPANY DATA. If absent, write a
   strategic principle — do NOT invent numbers.
2. Maximum 4 bullets. Each: one specific insight or proven fact. No intro sentences.
3. For data_grid_cards layout: include 3-4 metrics with real values from COMPANY DATA.
4. For COVER section (section_label = COVER): populate metadata and subtitle only.
5. PLAIN TEXT — no Markdown: no **, no *, no _, no #, no backticks.
6. ABSOLUTELY NO BRACKETS: never write [Name], [Company], [CEO], [Year] or any [X]
   notation. If a specific person/company is absent from data, use a generic descriptor:
   "a leading retail group", "the programme director". Never leave a placeholder.
7. Each bullet: MAXIMUM 110 characters. Keep concise.
8. visual_intent: corporate lifestyle photograph — NO charts, NO screens, NO text in image.

### OUTPUT — ONLY THIS JSON, nothing else:
{{
  "bullets": ["Plain text insight under 110 chars", "Plain text insight under 110 chars"],
  "subtitle": "Strategic tagline (COVER only, empty string otherwise)",
  "metrics": [{{"label": "KPI Name", "value": "X%", "growth": "+Y%"}}],
  "visual_intent": "Corporate photograph description without charts or screens",
  "visual_tags": ["keyword1", "keyword2", "keyword3"],
  "objective": "One sentence: what this slide achieves in the narrative",
  "metadata": {{"prepared_for": "Client Name", "confidential": true, "date": "Month YYYY"}}
}}""",
                "description": "Slide Content v2.0 — Strategic context, anti-placeholder, 110-char bullet limit."
            },

            # ─────────────────────────────────────────────────────
            # TEMPLATE MERGE ENGINE
            # All parameters are read once at job start via
            # TemplateMergeConfig.from_db() and passed to the
            # analyzer, content generator, and renderer.
            # To tune without redeploying: UPDATE system_configs SET value=... WHERE key=...
            # ─────────────────────────────────────────────────────
            {
                "key": "tm_shape_bg_area_threshold",
                "value": "0.80",
                "description": "Template Merge: non-placeholder shapes covering more than this fraction of slide area are treated as backgrounds and skipped."
            },
            {
                "key": "tm_shape_min_area_threshold",
                "value": "0.005",
                "description": "Template Merge: non-placeholder shapes smaller than this fraction of slide area are treated as decorative elements and skipped."
            },
            {
                "key": "tm_shape_min_text_length",
                "value": "3",
                "description": "Template Merge: non-placeholder shapes with existing text shorter than this (chars) are skipped."
            },
            {
                "key": "tm_hint_max_chars",
                "value": "200",
                "description": "Template Merge: maximum characters captured from a shape's existing text to use as content hint."
            },
            {
                "key": "tm_title_char_limit",
                "value": "80",
                "description": "Template Merge: default character limit for title slots."
            },
            {
                "key": "tm_footnote_char_limit",
                "value": "120",
                "description": "Template Merge: character limit for footnote/caption slots."
            },
            {
                "key": "tm_body_char_limit_min",
                "value": "80",
                "description": "Template Merge: minimum character limit for body slots (floor of the area-based estimate)."
            },
            {
                "key": "tm_body_char_limit_max",
                "value": "600",
                "description": "Template Merge: maximum character limit for body slots (ceiling of the area-based estimate)."
            },
            {
                "key": "tm_short_hint_threshold",
                "value": "15",
                "description": "Template Merge: hints shorter than this indicate a key-metric placeholder (e.g. '$45', '23%'); a tight char limit is applied."
            },
            {
                "key": "tm_short_hint_title_multiplier",
                "value": "3",
                "description": "Template Merge: char_limit = len(hint) × this multiplier for short-hint title slots."
            },
            {
                "key": "tm_short_hint_body_multiplier",
                "value": "4",
                "description": "Template Merge: char_limit = len(hint) × this multiplier for short-hint body slots."
            },
            {
                "key": "tm_chars_per_sq_inch",
                "value": "30",
                "description": "Template Merge: estimated characters per square inch used for body slot char_limit calculation."
            },
            {
                "key": "tm_footnote_area_fraction",
                "value": "0.03",
                "description": "Template Merge: shapes smaller than this fraction of slide area are classified as footnotes."
            },
            {
                "key": "tm_title_top_fraction",
                "value": "0.20",
                "description": "Template Merge: non-placeholder shapes in the top fraction of slide height are classified as titles."
            },
            {
                "key": "tm_rag_k",
                "value": "6",
                "description": "Template Merge: number of RAG chunks retrieved per slide."
            },
            {
                "key": "tm_rag_context_max_chars",
                "value": "3000",
                "description": "Template Merge: maximum characters of RAG context passed to the LLM per slide."
            },
            {
                "key": "tm_max_bullet_items",
                "value": "6",
                "description": "Template Merge: maximum bullet items when the LLM returns a list for a body slot."
            },
            {
                "key": "tm_preserve_max_hint_chars",
                "value": "50",
                "description": "Template Merge: non-placeholder shapes whose existing text is shorter than or equal to this (chars) are classified as PRESERVE — structural labels the LLM must not touch."
            },
            {
                "key": "tm_adapt_max_hint_chars",
                "value": "150",
                "description": "Template Merge: non-placeholder shapes with hint length between preserve_max and this value are classified as ADAPT — the LLM rewrites the data but keeps the same semantic territory and length."
            },
            {
                "key": "tm_preserve_keywords",
                "value": "confidential,proprietary,©,for reference only,preparado exclusivamente",
                "description": "Template Merge: comma-separated substrings; any match in a shape's existing text forces PRESERVE regardless of hint length (legal/confidential text)."
            },
            {
                "key": "tm_group_max_depth",
                "value": "3",
                "description": "Template Merge v2: maximum GroupShape nesting depth traversed when looking for text frames; groups beyond this depth are preserved as-is."
            },
            {
                "key": "tm_empty_rewrite_policy",
                "value": "blank",
                "description": "Template Merge v2: what to do when the LLM returns an empty string for a rewrite slot — 'blank' clears the template text (reported as unfilled), 'keep' leaves the original text in place."
            },
            {
                "key": "tm_outline_enabled",
                "value": "true",
                "description": "Template Merge v2 Fase 2: kill switch for the deck-level narrative plan call (1 LLM call per job, spends tokens). 'false' degrades to v1 behavior (hint-based RAG queries, no outline context)."
            },
            {
                "key": "tm_outline_rag_k",
                "value": "8",
                "description": "Template Merge v2 Fase 2: RAG chunks sampled (query = user prompt) as the knowledge overview for the outline planning call."
            },
            {
                "key": "tm_outline_context_max_chars",
                "value": "4000",
                "description": "Template Merge v2 Fase 2: maximum characters of RAG sample passed to the outline planning call."
            }
]


def seed_data():
    db = SessionLocal()
    try:
        for cfg in CONFIGS:
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
