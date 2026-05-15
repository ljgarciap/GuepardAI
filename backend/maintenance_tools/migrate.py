"""
migrate.py — PowerAI Database Migration
Crea las nuevas tablas brand_visual_dna y brand_artistic_essence
sin tocar las tablas existentes.

Uso:
    cd CleanArchitecture/backend
    source venv/bin/activate
    python migrate.py
"""
import sys
from sqlalchemy import text, inspect
from database import engine, Base
import models  # noqa: F401 — importar para registrar todos los modelos en Base.metadata


def table_exists(conn, table_name: str) -> bool:
    inspector = inspect(conn)
    return table_name in inspector.get_table_names()


def run_migration():
    print("[Migrate] Iniciando migración PowerAI...", flush=True)

    with engine.connect() as conn:
        # Verificar extensión pgvector (requerida por corporate_knowledge)
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.commit()
            print("[Migrate] ✓ Extensión pgvector verificada.", flush=True)
        except Exception as e:
            print(f"[Migrate] ⚠ pgvector: {e}", flush=True)

        # Tablas a crear (solo las nuevas)
        new_tables = ["brand_visual_dna", "brand_artistic_essence"]

        for tname in new_tables:
            if table_exists(conn, tname):
                print(f"[Migrate] → {tname}: ya existe, omitiendo.", flush=True)
            else:
                print(f"[Migrate] → {tname}: CREANDO...", flush=True)

        # Tablas existentes que deben conservarse
        existing_tables = [
            "brand_styles",
            "ingestion_jobs",
            "generation_jobs",
            "corporate_knowledge",
        ]
        for tname in existing_tables:
            status = "encontrada ✓" if table_exists(conn, tname) else "NO ENCONTRADA ⚠"
            print(f"[Migrate] → {tname}: {status}", flush=True)

    # Crear solo las tablas que faltan (SQLAlchemy no toca las existentes con checkfirst)
    Base.metadata.create_all(bind=engine, checkfirst=True)

    print("\n[Migrate] ✓ Migración completada.", flush=True)
    print("[Migrate] Tablas activas:", flush=True)

    with engine.connect() as conn:
        inspector = inspect(conn)
        for tname in sorted(inspector.get_table_names()):
            print(f"           - {tname}", flush=True)


if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"[Migrate] ✗ Error: {e}", flush=True)
        sys.exit(1)
