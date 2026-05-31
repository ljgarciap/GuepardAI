import sys
import os

# Add backend to path
sys.path.append(os.path.abspath("backend"))

from database import SessionLocal
import models
from services.rendering.premium_visual_agent import PremiumVisualAgent

db = SessionLocal()
job = db.query(models.GenerationJob).order_by(models.GenerationJob.id.desc()).first()

if job:
    print(f"Testing for job {job.id}")
    agent = PremiumVisualAgent(db, job.id, "uploads")
    brand_dna = db.query(models.BrandVisualDna).filter(models.BrandVisualDna.brand_id == job.brand_id).first()
    patterns = agent._load_patterns(brand_dna)
    
    slides_data = [
        {"slide_number": 1, "title": "Test 1", "pattern_type": "editorial_split"},
        {"slide_number": 2, "title": "Test 2", "pattern_type": "editorial_split"}
    ]
    
    try:
        res = agent._vision_adjust_loop(slides_data, patterns, brand_dna, [])
        print("Success:", res)
    except Exception as e:
        import traceback
        traceback.print_exc()
else:
    print("No job found")

db.close()
