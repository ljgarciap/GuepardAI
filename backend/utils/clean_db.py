import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal, engine
import models
from sqlalchemy import text

db = SessionLocal()
try:
    tables_to_truncate = [
        "generation_jobs",
        "presentation_slides",
        "art_director_decisions",
        "brand_visual_dna",
        "presentation_documents",
        "brand_assets"
    ]
    for table in tables_to_truncate:
        try:
            db.execute(text(f"TRUNCATE TABLE {table} CASCADE;"))
            print(f"Truncated {table}")
        except Exception as e:
            print(f"Could not truncate {table}: {e}")
            db.rollback()
    db.commit()
    print("Database cleaned successfully!")
except Exception as e:
    print(f"Error cleaning DB: {e}")
finally:
    db.close()
