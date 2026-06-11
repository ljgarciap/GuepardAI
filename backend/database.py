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
        conn.commit()
except Exception as e:
    print(f"  [DB] Warning: In-place migration skipped: {e}")

# Dependency function to manage opening and closing DB connections
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
