import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# PostgreSQL (pgvector) connection URL
# Uses `postgresql+psycopg` for the modern drivers (psycopg3)
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://root:root@localhost:5432/ai_db")

# Engine handles the PostgreSQL connection pool
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# Session maker for CRUD operations in each request
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for SQLAlchemy ORM models
Base = declarative_base()

# Dependency function to manage opening and closing DB connections
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
