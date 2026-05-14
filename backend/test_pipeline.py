import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from services.layout_engine import generate_presentation_flow

db = SessionLocal()
brand = db.query(models.Brand).filter(models.Brand.name == 'Tesco').first()
job = models.GenerationJob(brand_id=brand.id, status='pending')
db.add(job)
db.commit()

req_data = {
    "prompt": "Strategic Value of Tesco Clubcard - Focus on Data to Growth and $500M ROI",
    "audience": "Board of Directors",
    "tone": "Authoritative and concise",
    "num_slides": 3
}
generate_presentation_flow(db, job.id, req_data)
print(f"Job {job.id} completed. File at {job.pptx_path}")
