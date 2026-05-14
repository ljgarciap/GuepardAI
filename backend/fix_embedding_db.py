import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from sqlalchemy.orm import Session
from database import SessionLocal
import models

db = SessionLocal()
config = db.query(models.SystemConfig).filter(models.SystemConfig.key == 'embedding_model_chain').first()
if config:
    config.value = "mistral-embed,models/embedding-001"
    db.commit()
    print("Updated embedding config in DB.")
db.close()
