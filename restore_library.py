import os
import sys
sys.path.append('backend')
import models
from database import SessionLocal
from services.asset_library_service import register_asset
import glob

def restore():
    db = SessionLocal()
    # Identificar la marca Tesco
    tesco = db.query(models.Brand).filter(models.Brand.name == 'Tesco').first()
    if not tesco:
        print("Tesco brand not found.")
        return
    
    brand_id = tesco.id
    print(f"Restoring assets for {tesco.name} (ID: {brand_id})...")
    
    # Buscar todos los archivos asset_*.png en uploads
    asset_files = glob.glob("backend/uploads/asset_*.png")
    print(f"Found {len(asset_files)} physical assets to restore.")
    
    for i, file_path in enumerate(asset_files):
        # Convertir a ruta relativa para register_asset si es necesario
        # register_asset espera la ruta al archivo
        try:
            print(f"[{i+1}/{len(asset_files)}] Restoring: {os.path.basename(file_path)}...")
            # Forzar el tagging para que se generen los embeddings nuevos
            register_asset(
                db, 
                brand_id=brand_id, 
                file_path=file_path, 
                category="photos", 
                force_tagging=True,
                source_doc="Restored from Quality Reset",
                manual_tags=["tesco", "restored"]
            )
        except Exception as e:
            print(f"Error restoring {file_path}: {e}")
            
    print("Restore complete. Assets are now semantically searchable.")

if __name__ == "__main__":
    restore()
