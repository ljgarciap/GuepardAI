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
                "key": "agency_name",
                "value": "L - Founders of Loyalty",
                "description": "Nombre de la empresa que genera la presentación (Branding de Autor)."
            },
            {
                "key": "agency_logo_path",
                "value": "uploads/L-founders_logo.png",
                "description": "Ruta al logo de la agencia para el footer/firma."
            },
            {
                "key": "asset_score_threshold",
                "value": "0.45",
                "description": "Umbral mínimo de similitud semántica para aceptar asset. 0.45 es el punto dulce para evitar logos pero permitir fotos reales."
            },
            {
                "key": "embedding_model_chain",
                "value": "mistral-embed,models/gemini-embedding-2",
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
            # API KEYS Y CREDENCIALES (Protegidas)
            # ─────────────────────────────────────────────────────
            {
                "key": "mistral_api_key",
                "value": "",
                "description": "API Key de Mistral (requerida para mistral-embed y mistral-large).",
                "preserve_existing": True
            },
            {
                "key": "gemini_api_key",
                "value": "",
                "description": "API Key de Google Gemini (requerida para multimodal y embeddings secundarios).",
                "preserve_existing": True
            },
            {
                "key": "metric_value_scaling",
                "value": """# Metric Value (v24.2: Intelligent Scaling)
            val = str(m.get("value", ""))
            v_len = len(val)
            if v_len < 6: v_size = 44
            elif v_len < 12: v_size = 28
            elif v_len < 20: v_size = 18
            else: v_size = 12
            
            self.add_text(slide, val, x_pos, y_pos + self.h(1), w_pos, self.h(11), 
                          size=v_size, bold=True, color=text_color, align=PP_ALIGN.CENTER, v_align=MSO_ANCHOR.MIDDLE)""",
                "description": "Logic for dynamic text sizing in metrics to prevent overlap.",
                "preserve_existing": True
            },
            {
                "key": "anthropic_api_key",
                "value": "",
                "description": "API Key de Anthropic (Claude 3.5 Sonnet, etc.).",
                "preserve_existing": True
            },
            {
                "key": "gcp_project_id",
                "value": "",
                "description": "ID del Proyecto de Google Cloud Platform (Para Vertex AI, Imagen 3, etc).",
                "preserve_existing": True
            },
            {
                "key": "gcp_location",
                "value": "us-central1",
                "description": "Ubicación de GCP para Vertex AI.",
                "preserve_existing": True
            },

            # ─────────────────────────────────────────────────────
            # PROMPT: ANALISTA ESTRATÉGICO v8.5
            # ─────────────────────────────────────────────────────
            {
                "key": "prompt_analyst_v1",
                "value": """You are a Strategic Design Analyst for executive presentations (Board of Directors level).
Analyze the slide content and the RAG Context to define the Visual Strategy.

SLIDE CONTENT:
Title: {slide_title}
Bullets: {bullets}
RAG Context: {rag_context}

GRAMMAR TYPE RULES (Pick the most IMPACTFUL):
- "composition_hero": ONLY for Title slides or major Section Breaks. 
- "composition_split": The workhorse for content. Use when a strong image supports the text.
- "big_metric": Use when a SINGLE number is the main hero (e.g. "$500M ROI").
- "composition_quote": CRITICAL for testimonials or single powerful strategic pillars. Use for emotional/authority impact.
- "data_grid_cards": ONLY for dashboards with 3-6 metrics. If less than 3, use "composition_pillars" or "composition_split".
- "composition_pillars": Use for exactly 3-4 distinct strategic columns.

STRATEGIC DIRECTIVE:
1. NARRATIVE FLOW (CRITICAL): DO NOT use the same layout twice in a row. If the previous was "data_grid_cards", MUST use "composition_split", "composition_pillars" or "composition_quote".
2. VISUAL INTENT: Describe a CORPORATE photography scene. DO NOT ask for charts, text, or graphics. (e.g., "Modern architectural lobby with glass and steel").
3. METRIC EXTRACTION: If you see a key KPI, extract it for the "metric_value" field.
4. VARIETY: Prioritize "composition_split" for most slides to maintain a cinematic quality. Use "data_grid_cards" only when the RAG context contains 4+ distinct numbers.

OUTPUT JSON:
{{
  "visual_intent": "Brief description of a clean, text-free corporate photo",
  "suggested_keywords": ["keyword1", "keyword2"],
  "grammar_type": "...",
  "requires_hero": false,
  "metric_value": null,
  "narrative_tone": "authoritative"
}}""",
                "description": "Strategic Analyst v8.6 — High-Impact Selection Logic."
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
                "value": """### ROLE: SENIOR STRATEGIC PARTNER & LEAD CONSULTANT for {agency_name}
### CORE MISSION (PRIORITY 1): "{topic}"
### AUDIENCE: Board of Directors / CEO Level
### BRAND CONTEXT: {brand_name}
### OUTPUT LANGUAGE: {target_lang} (MANDATORY)

### STRATEGIC MANDATE:
Execute the CORE MISSION with absolute precision. You are a High-End Strategy Consultant. Your goal is to articulate the "SO WHAT?"—don't just report data; interpret it for strategic impact according to the specific requirements of the CORE MISSION.

### CORE PRINCIPLES (The Elite Consultancy Standard):
1. THE "SO WHAT?" FACTOR: For every metric or fact, explain the business implication. (e.g., instead of "84% penetration", use "84% penetration: dominant market leverage to drive future growth").
2. EXTREME CONCISION: Use high-impact sentence fragments. No fluff.
3. AUTHORITATIVE PERSPECTIVE: Speak as the expert. You define the strategy.
4. EVIDENCE-BASED: Use specific figures ($, %, ROI) from the RAG context.
5. NARRATIVE FLOW: Strategic Hook -> Deep-Dive Reality -> ROI Proof -> Testimonials -> The Next Chapter.

### SOURCE CONTEXT (RAG):
{rag_context}

### TONE & STYLE:
Confident, hyper-concise, and strategic. Avoid "corporate speak" clichés; use precise commercial terminology.
{tone_guideline}

### LAYOUT CATALOG:
- "composition_hero": Cover and Section Breaks.
- "composition_split": Content with supporting image.
- "composition_quote": CEO/Executive testimonials (MANDATORY for impact).
- "big_metric": Single major KPI highlight with strategic label.
- "data_grid_cards": Use for "Key Performance Indicators" or "Strategic Benchmarks". REQUIRES "metrics" array.
- "composition_pillars": 3-4 core strategic pillars.

### CONTENT RULES:
- Title: Strategic, outcome-oriented (max 40 chars).
- Bullets: Actionable, result-driven (max 80 chars, max 4 per slide).
- Metrics: Provide structured data for cards: [ {{"label": "...", "value": "...", "growth": "..."}} ].
- **IMAGE PROMPTS (CRITICAL):** Request ONLY "Clean, high-end professional corporate photography, commercial aesthetic, minimalist composition". 
  **STRICT FORBIDDEN:** DO NOT request charts, text, labels, or people holding signs. NO GRAPHICS inside images.

### TASK:
Analyze the RAG Context and the user's specific CORE MISSION to generate a strategic presentation (10-15 slides).
Absolute priority to the specific instructions in the "{topic}" MISSION while maintaining this elite consultancy framework.

### MANDATORY JSON STRUCTURE (OUTPUT ONLY THIS):
{{
  "slides": [
    {{
      "title": "Impactful Slide Title",
      "bullets": ["Strategic bullet 1 (So what?)", "Strategic bullet 2 (Business impact)"],
      "layout_type": "composition_split",
      "metrics": [ {{"label": "KPI", "value": "20%", "growth": "+5%"}} ],
      "section_label": "STRATEGY"
    }}
  ]
}}

### CONTENT INTEGRITY RULES:
1. NO EMPTY SLIDES: Every slide MUST have a non-empty title and at least 2 high-impact bullets.
2. NO PLACEHOLDERS: If you don't have enough data for a slide, don't generate it.
3. DATA RECOVERY: If specific metrics are missing in RAG, use qualitative strategic observations instead of empty metrics.""",
                "description": "Content Synthesizer v26.2 — Priority User Mission & Scaling Logic."
            },



        ]

        for cfg in configs:
            existing = db.query(models.SystemConfig).filter(
                models.SystemConfig.key == cfg["key"]
            ).first()
            if existing:
                if not cfg.get("preserve_existing", False):
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
