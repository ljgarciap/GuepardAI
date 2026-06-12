import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# PostgreSQL (pgvector) connection URL
# Uses `postgresql+psycopg` for the modern drivers (psycopg3)
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://root:root@localhost:5432/ai_db")

# Engine handles the PostgreSQL connection pool (v40.0 - Parallel Ready)
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=20,        # Aumentar para soportar hilos paralelos
    max_overflow=10,     # Permitir exceso temporal
    pool_timeout=30      # Esperar 30s antes de fallar
)

# Session maker for CRUD operations in each request
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for SQLAlchemy ORM models
Base = declarative_base()

# AUTOMATIC EXTENSION INITIALIZATION (v37.0)
from sqlalchemy import text
try:
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()
        print("  [DB] Success: pgvector extension is ACTIVE.")
except Exception as e:
    print(f"  [DB] Warning: Could not initialize pgvector: {e}")

# LIGHTWEIGHT IN-PLACE MIGRATIONS
# create_all() no altera tablas existentes; estos ALTER idempotentes cubren
# bases de datos ya desplegadas. Solo columnas nullable/default (operación segura).
try:
    with engine.connect() as conn:
        # Selección de Imágenes v1
        conn.execute(text(
            "ALTER TABLE brand_assets ADD COLUMN IF NOT EXISTS visual_profile JSON;"
        ))
        # Fixes de Resiliencia (F4)
        conn.execute(text(
            "ALTER TABLE generation_jobs ADD COLUMN IF NOT EXISTS qa_forced INTEGER DEFAULT 0;"
        ))
        # Gestión de Portfolios (renombrado)
        conn.execute(text(
            "ALTER TABLE generation_jobs ADD COLUMN IF NOT EXISTS display_name VARCHAR(120);"
        ))
        # Calidad de Selección de Imágenes v2 (dedup perceptual)
        conn.execute(text(
            "ALTER TABLE brand_assets ADD COLUMN IF NOT EXISTS perceptual_hash VARCHAR(32);"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_brand_assets_perceptual_hash ON brand_assets (perceptual_hash);"
        ))
        # ingestion_jobs: columnas agregadas al modelo sin ALTER previo. Sin esto,
        # el ORM selecciona columnas que la tabla desplegada no tiene y la ingesta
        # de knowledge revienta con "Could not locate column in row for ...".
        conn.execute(text(
            "ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS visibility_scope VARCHAR(20) DEFAULT 'exclusive';"
        ))
        conn.execute(text(
            "ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;"
        ))
        conn.commit()
except Exception as e:
    print(f"  [DB] Warning: In-place migration skipped: {e}")

def reconcile_additive_columns():
    """
    Auto-cura el drift ADITIVO de schema en BDs ya desplegadas.

    create_all() crea tablas nuevas pero NUNCA altera las existentes, así que
    cada columna agregada a un modelo rompe las BDs viejas hasta que alguien
    escribe un ALTER a mano (como los de arriba). Esta función cierra ese hueco
    de forma genérica: por cada tabla mapeada que YA existe, compara las columnas
    del modelo contra las reales en la BD y emite
    `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (siempre nullable, operación segura
    sobre tablas con datos) para las que falten.

    Solo aditivo y tolerante: nunca borra ni cambia tipos; un tipo que no compila
    o un ALTER que falla se loguea y NO bloquea el arranque. Debe llamarse
    DESPUÉS de Base.metadata.create_all() (con los modelos ya importados) — ver
    el startup de main.py. En una BD nueva no hace nada (create_all ya dejó todo
    completo); en una desplegada y vieja, la pone al día sin perder datos.
    """
    from sqlalchemy import inspect as sa_inspect
    try:
        inspector = sa_inspect(engine)
        existing_tables = set(inspector.get_table_names())
    except Exception as e:
        print(f"  [DB] Schema reconcile skipped (inspect failed): {e}")
        return

    added = 0
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # tabla nueva: create_all ya la creó completa
        try:
            live_cols = {c["name"] for c in inspector.get_columns(table.name)}
        except Exception:
            continue
        for col in table.columns:
            if col.name in live_cols:
                continue
            try:
                col_type = col.type.compile(dialect=engine.dialect)
            except Exception:
                print(f"  [DB] Reconcile: skip {table.name}.{col.name} (uncompilable type)")
                continue
            ddl = f'ALTER TABLE {table.name} ADD COLUMN IF NOT EXISTS "{col.name}" {col_type}'
            try:
                with engine.begin() as conn:
                    conn.execute(text(ddl))
                added += 1
                print(f"  [DB] Reconcile: added {table.name}.{col.name} ({col_type})")
            except Exception as e:
                print(f"  [DB] Reconcile: failed on {table.name}.{col.name}: {e}")
    if added:
        print(f"  [DB] Schema reconcile: {added} additive column(s) applied.")


# Dependency function to manage opening and closing DB connections
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
