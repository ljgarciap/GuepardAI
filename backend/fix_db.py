
import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://root:root@localhost:5432/ai_db")
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    print("Checking database schema...")
    try:
        conn.execute(text("ALTER TABLE brand_artistic_essence ADD COLUMN structural_archetypes JSONB;"))
        conn.commit()
        print("Success: Column 'structural_archetypes' added to brand_artistic_essence.")
    except Exception as e:
        print(f"Error or already exists: {e}")

    try:
        conn.execute(text("ALTER TABLE brand_visual_dna ADD COLUMN IF NOT EXISTS raw_extraction JSONB;"))
        conn.commit()
    except:
        pass
