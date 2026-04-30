
import os
from sqlalchemy import create_engine, text
from database import Base, engine
import models

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://root:root@localhost:5432/ai_db")
engine = create_engine(DATABASE_URL)

def clean_slate():
    print("--- TABULA RASA INITIATED ---")
    
    print("Dropping all existing tables...")
    models.Base.metadata.drop_all(bind=engine)
    
    print("Recreating all tables with new schema...")
    models.Base.metadata.create_all(bind=engine)
    
    with engine.connect() as conn:
        print("Initializing pgvector and corporate_knowledge table...")
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS corporate_knowledge (
                id SERIAL PRIMARY KEY,
                content TEXT,
                metadata JSONB,
                embedding VECTOR(1024)
            );
        """))
        conn.commit()
    print("--- CLEAN SLATE COMPLETED ---")

if __name__ == "__main__":
    clean_slate()
