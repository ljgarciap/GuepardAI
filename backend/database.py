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

# Dependency function to manage opening and closing DB connections
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
