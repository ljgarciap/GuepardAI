import sys
import os

# Allow imports from backend/ when running this script
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
import models

db = SessionLocal()
try:
    deleted_essences = db.query(models.BrandArtisticEssence).delete()
    deleted_patterns = db.query(models.BrandPremiumVisualPattern).delete()
    db.commit()
    print(f"Deleted {deleted_essences} essences and {deleted_patterns} patterns.")
except Exception as e:
    db.rollback()
    print(f"Error: {e}")
finally:
    db.close()
