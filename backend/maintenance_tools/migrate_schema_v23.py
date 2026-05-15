import database
from sqlalchemy import text

engine = database.engine
queries = [
    "ALTER TABLE generation_jobs ADD COLUMN IF NOT EXISTS style_id INTEGER;",
    "ALTER TABLE presentation_slides ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'pending';",
    "ALTER TABLE presentation_slides ADD COLUMN IF NOT EXISTS planning_json JSONB;"
]

print("Starting schema migration...")
with engine.connect() as conn:
    for sql in queries:
        try:
            conn.execute(text(sql))
            print(f"Success: {sql}")
        except Exception as e:
            print(f"Failed: {sql} | Error: {e}")
    conn.commit()
print("Migration completed.")
