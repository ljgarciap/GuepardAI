import sys
import os
import json

# Allow imports from backend/ when running this script
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
import models

db = SessionLocal()
job = db.query(models.GenerationJob).order_by(models.GenerationJob.id.desc()).first()

if job:
    print(f"Job ID: {job.id}")
    print(f"Brand ID: {job.brand_id}")
    
    essence = db.query(models.BrandArtisticEssence).filter(models.BrandArtisticEssence.brand_id == job.brand_id).order_by(models.BrandArtisticEssence.updated_at.desc()).first()
    if essence:
        print("ESSENCE VISUAL STRATEGY:")
        print(essence.visual_strategy)
        print("ESSENCE TYPOGRAPHY STYLE:")
        print(essence.composition_rules.get("typography_style", "N/A"))
        print("RAW VISION RESPONSE:")
        print(json.dumps(essence.raw_vision_response, indent=2)[:500])
    
    patterns = db.query(models.BrandPremiumVisualPattern).filter(models.BrandPremiumVisualPattern.brand_id == job.brand_id).order_by(models.BrandPremiumVisualPattern.updated_at.desc()).first()
    if patterns:
        print("PREMIUM VISUAL PATTERNS:")
        print(json.dumps(patterns.patterns_json, indent=2))
    else:
        print("NO PREMIUM VISUAL PATTERNS IN DB.")
else:
    print("No jobs found")

db.close()
