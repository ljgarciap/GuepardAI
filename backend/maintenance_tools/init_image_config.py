from database import SessionLocal
import models

def init_config():
    db = SessionLocal()
    try:
        key = "model_image_gen"
        val = "imagen-3.0-generate-001"
        exists = db.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
        if not exists:
            db.add(models.SystemConfig(key=key, value=val))
            db.commit()
            print(f"Config {key} initialized to {val}")
        else:
            print(f"Config {key} already exists.")
    finally:
        db.close()

if __name__ == "__main__":
    init_config()
