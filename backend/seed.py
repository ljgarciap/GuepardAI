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
