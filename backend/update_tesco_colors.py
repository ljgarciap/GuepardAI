import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from sqlalchemy.orm import Session
from database import SessionLocal
import models

db = SessionLocal()
brand = db.query(models.Brand).filter(models.Brand.name == 'Tesco').first()
if brand:
    dna = db.query(models.BrandVisualDna).filter(models.BrandVisualDna.brand_id == brand.id).first()
    if dna:
        dna.primary_color = "#002D62" # Deep Replit Navy
        dna.secondary_color = "#E31837" # Tesco Red
        dna.background_color = "#FFFFFF" # White
        db.commit()
        print("Tesco colors updated successfully.")
    else:
        print("DNA not found")
else:
    print("Tesco brand not found")
db.close()
