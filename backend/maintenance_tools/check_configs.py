from database import SessionLocal
import models

db = SessionLocal()
try:
    configs = db.query(models.SystemConfig).all()
    for c in configs:
        print(f"Key: {c.key} | Value: {c.value}")
finally:
    db.close()
