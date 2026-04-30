"""
seed.py — PowerAI
Script de datos iniciales. Idempotente: se puede correr múltiples veces sin duplicar.
Uso: ./venv/bin/python3 seed.py
"""
from database import SessionLocal
import models


def seed_data():
    db = SessionLocal()
    try:
        print("[Seeder] Iniciando sembrado de datos...")

        # 1. Marca Maestra / Pública (ID -1)
        public_brand = db.query(models.Brand).filter(models.Brand.id == -1).first()
        if not public_brand:
            print("  [+] Creando Marca Pública (ID -1)...")
            db.add(models.Brand(
                id=-1,
                name="Public Library",
                about="Contenedor global para activos y conocimiento público.",
                core_value="Universal Knowledge"
            ))
            db.commit()
        else:
            print("  [=] Marca Pública ya existe, omitiendo.")

        # 2. Idiomas (Prioridad correcta)
        langs = [
            {"code": "UK",  "name": "English (UK)",    "priority": 1},
            {"code": "USA", "name": "English (USA)",   "priority": 2},
            {"code": "FR",  "name": "Français",        "priority": 3},
            {"code": "ES",  "name": "Español (LATAM)", "priority": 4},
        ]
        for l in langs:
            existing = db.query(models.Language).filter(models.Language.code == l["code"]).first()
            if existing:
                existing.priority = l["priority"]  # Actualizar prioridad si existe
                print(f"  [=] Idioma {l['name']} actualizado (prioridad {l['priority']}).")
            else:
                db.add(models.Language(**l))
                print(f"  [+] Idioma {l['name']} creado.")

        # 3. Configuraciones de Sistema (Modelos Reales de Producción)
        # Eliminar placeholders errados de ejecuciones previas
        stale_keys = ["default_llm_model", "vision_llm_model", "max_slides_default"]
        db.query(models.SystemConfig).filter(
            models.SystemConfig.key.in_(stale_keys)
        ).delete(synchronize_session=False)

        configs = [
            {
                "key": "extraction_synthesis_model",
                "value": "mistral/mistral-large-latest,models/gemini-2.5-flash",
                "description": "Cadena de modelos para síntesis de texto y RAG"
            },
            {
                "key": "art_director_model",
                "value": "models/gemini-2.5-flash,mistral/mistral-large-latest",
                "description": "Cadena de modelos para decisiones del Art Director"
            },
            {
                "key": "extraction_vision_model",
                "value": "models/gemini-2.5-flash",
                "description": "Modelo Vision para extracción de DNA Visual (PPTX/PDF)"
            },
            {
                "key": "embedding_model_chain",
                "value": "mistral-embed,models/gemini-embedding-2",
                "description": "Cadena de embeddings para búsqueda semántica RAG"
            },
            {
                "key": "vector_dim",
                "value": "1024",
                "description": "Dimensión de los vectores de embedding"
            },
            {
                "key": "global_fallback_model",
                "value": "models/gemini-2.5-flash",
                "description": "Modelo de seguridad absoluta si fallan las cadenas principales"
            },
            {
                "key": "fallback_embedding_model",
                "value": "models/text-embedding-004",
                "description": "Modelo de embedding de seguridad"
            },
            {
                "key": "prompt_art_director_v1",
                "value": """### ROLE: SENIOR BRAND ART DIRECTOR
{strategic_context}

### BRAND RULEBOOK (STRICT ADHERENCE):
{brand_rulebook}

### RECENT VISUAL THEMES (DIVERSITY PROTECTION):
{used_descriptions}

### OPERATIONAL CONSTRAINTS:
1. NO OVERLAP: Maintain strict margins between title, body, and assets.
2. DATA COMPONENTS: If the slide content contains metrics or comparisons, you MUST request a 'table'.

Slide Title: {slide_title}
Content: {bullets}

AVAILABLE ASSETS (Ranked by relevance):
{found_assets}

INSTRUCTION: Pick a layout and assign assets.

Return ONLY JSON:
{{ 
  "layout_slug": "marketing-hero | split-right | full-bleed | two-column | asymmetric-overlay | editorial-magazine | dark-hero", 
  "primary_asset_id": INTEGER_ID_OR_NULL, 
  "accent_id": INTEGER_ID_OR_NULL,
  "table": {{
     "data": [["Header1", "Header2"], ["Row1Col1", "Row1Col2"]],
     "reasoning": "Why a table is needed here."
  }},
  "reasoning": "Strategy-driven explanation."
}}""",
                "description": "Prompt dinámico para el Art Director"
            },
            {
                "key": "prompt_analyst_v1",
                "value": """Analyze these brand manual slides and extract the VISUAL DNA and a DESIGN RULEBOOK.

1. VISUAL DNA (Structural): Sidebars, headers, footers, corner styles, and spacing.
2. DESIGN RULEBOOK (Behavioral): Extract specific laws mentioned in the manual. 
   - Examples: "Fruits only in titles", "Never overlap text on faces", "Use only black backgrounds for metrics".
   - Write this rulebook in Markdown format.

OUTPUT ONLY JSON:
{
  "visual_strategy": "string description",
  "branding_rulebook": "Markdown string containing the extracted design laws",
  "structural_archetypes": {
    "persistent_blocks": [
       { "role": "sidebar", "geometry": {"top":0, "left":0, "width":20, "height":100}, "color_source": "primary" }
    ]
  },
  "design_gestures": { "corner_style": "sharp", "spacing": "airy" }
}""",
                "description": "Prompt dinámico para el Analista de Marca"
            },
            {
                "key": "prompt_classifier_v1",
                "value": """Analyze this image with DESIGNER RIGOR and return a JSON with:
- 'category': Choose one: 
    * 'lifestyle_photos': Complex scenes, people, stores, or environments.
    * 'design_elements': Single isolated objects (fruits, products), icons, or accents on solid/transparent backgrounds.
    * 'logos': Brand identities.
    * 'backgrounds': Textures or full-page backgrounds.
    * 'noise': Blank, blurry, low-quality, off-brand, or useless images. If the image does NOT align with the brand strategy, it is noise.
- 'is_person': boolean.
- 'background_type': 'transparent', 'solid_white', 'solid_black', 'complex', or 'other'.
- 'description': CRITICAL INSTRUCTION: Provide a CONCISE, analytical description (Max 3 sentences). Focus strictly on the strategic value, emotional tone, and subject matter, rather than exhaustive physical details.
- 'tags': 5 semantic keywords.""",
                "description": "Prompt dinámico para clasificación de activos"
            }
        ]
        for c in configs:
            existing = db.query(models.SystemConfig).filter(
                models.SystemConfig.key == c["key"]
            ).first()
            if existing:
                existing.value = c["value"]
                existing.description = c["description"]
                print(f"  [=] Config '{c['key']}' actualizada.")
            else:
                db.add(models.SystemConfig(**c))
                print(f"  [+] Config '{c['key']}' creada.")

        db.commit()
        print("[Seeder] ✅ Sembrado completado exitosamente.")

    except Exception as e:
        print(f"[Seeder] ❌ ERROR: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_data()
