"""
populate_library.py — PowerAI
Script de emergencia para poblar la biblioteca de activos de Tesco.
"""
import os
import json
from database import SessionLocal, engine, Base
import models
from services.asset_library_service import register_asset

def populate():
    # Asegurar que las tablas existan
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        brand = db.query(models.BrandVisualDna).filter(
            models.BrandVisualDna.source_filename == "Tesco Style_2.pptx"
        ).first()
        
        if not brand:
            print("Error: No se encontró la marca Tesco en la DB.")
            return

        print(f"--- Poblando Biblioteca para Brand ID: {brand.id} (Tesco) ---")
        
        # Escanear carpeta uploads para esta marca
        upload_dir = "uploads"
        # Buscamos archivos que empiecen con el nombre de la marca (patrón de extracción)
        prefix = "brand_style_Tesco Style_2.pptx"
        
        files = [f for f in os.listdir(upload_dir) if f.startswith(prefix)]
        print(f"Se encontraron {len(files)} archivos para procesar.")

        final_library_assets = {"photos": [], "logos": [], "icons": []}

        for i, filename in enumerate(files):
            file_path = os.path.join(upload_dir, filename)
            category = "photos"
            if "logo" in filename.lower(): category = "logos"
            elif "icon" in filename.lower(): category = "icons"
            
            print(f"[{i+1}/{len(files)}] Registrando: {filename}...")
            try:
                # Usamos una sub-transacción para cada activo
                asset_record = register_asset(db, brand.id, file_path, category=category)
                final_library_assets[category].append({
                    "id": asset_record.id,
                    "path": os.path.basename(asset_record.local_path),
                    "tags": asset_record.tags,
                    "description": asset_record.description
                })
                # Commit individual para asegurar progreso
                db.commit()
            except Exception as e:
                db.rollback() # Limpiar estado si falla
                print(f"  ✗ Fallo en registro de {filename}: {e}")

        # Actualizar el JSON de activos del DNA final
        brand.extracted_assets = final_library_assets
        db.commit()
        print(f"\n✓ BIBLIOTECA POBLADA CON ÉXITO: {sum(len(v) for v in final_library_assets.values())} activos registrados.")

    finally:
        db.close()

if __name__ == "__main__":
    populate()
