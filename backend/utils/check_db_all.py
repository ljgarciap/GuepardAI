import sys
import os
import json

# Allow imports from backend/ when running this script
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
import models

db = SessionLocal()
essences = db.query(models.BrandArtisticEssence).all()
print("ALL ESSENCES:")
for e in essences:
    print(f"Brand ID: {e.brand_id}")
    print(e.visual_strategy)
    
patterns = db.query(models.BrandPremiumVisualPattern).all()
print("\nALL PATTERNS:")
for p in patterns:
    print(f"Brand ID: {p.brand_id}")
    print(json.dumps(p.patterns_json))

db.close()
