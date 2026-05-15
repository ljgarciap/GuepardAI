
from database import SessionLocal
import models
import os

def fix_paths():
    db = SessionLocal()
    try:
        assets = db.query(models.BrandAsset).all()
        count = 0
        for a in assets:
            # Si el path no tiene 'uploads/' pero el archivo existe dentro de uploads/
            if not a.local_path.startswith("uploads/"):
                new_path = f"uploads/{a.local_path}"
                # Verificar si el archivo existe en esa nueva ruta (dentro del contenedor)
                if os.path.exists(os.path.join("/app", new_path)):
                    a.local_path = new_path
                    count += 1
        db.commit()
        print(f"✓ Corrected {count} asset paths in database.")
    finally:
        db.close()

if __name__ == "__main__":
    fix_paths()
