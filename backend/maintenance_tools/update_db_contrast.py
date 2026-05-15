from database import engine
from sqlalchemy import text
with engine.connect() as conn:
    conn.execute(text("ALTER TABLE brand_visual_dna ADD COLUMN IF NOT EXISTS text_on_dark VARCHAR DEFAULT '#FFFFFF'"))
    conn.commit()
    print('[DB] Contrast column added successfully')
