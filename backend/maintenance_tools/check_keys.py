import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from sqlalchemy.orm import Session
from database import SessionLocal
import models

db = SessionLocal()
configs = db.query(models.SystemConfig).all()
for c in configs:
    if "key" in c.key.lower():
        print(f"Key in DB: {c.key} = {c.value[:5]}...")
db.close()
