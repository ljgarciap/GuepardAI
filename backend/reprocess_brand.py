import os
import json
from dotenv import load_dotenv
from services.visual_dna_service import extract_visual_dna
from services.artistic_essence_service import extract_artistic_essence
from database import SessionLocal
import models

load_dotenv()

def reprocess(filename, source_path):
    print(f"--- Reprocesando: {filename} ---")
    
    # 1. Extraer Visual DNA
    print("1/2 Extrayendo DNA Visual (Colores, Fuentes)...")
    dna = extract_visual_dna(source_path, "uploads")
    
    # 2. Extraer Artistic Essence (Vision LLM)
    print("2/2 Analizando Esencia Artística (Vision LLM con Claude 3.7/Gemini 2.5)...")
    essence = extract_artistic_essence(source_path, "uploads")
    
    # 3. Persistir en DB
    db = SessionLocal()
    try:
        # DNA
        record_dna = db.query(models.BrandVisualDna).filter(models.BrandVisualDna.source_filename == filename).first()
        if not record_dna:
            record_dna = models.BrandVisualDna(source_filename=filename)
            db.add(record_dna)
        
        record_dna.primary_color = dna.get("primary_color", "#333333")
        record_dna.secondary_color = dna.get("secondary_color", "#666666")
        record_dna.background_color = dna.get("background_color", "#FFFFFF")
        record_dna.text_main_color = dna.get("text_main_color", "#111111")
        record_dna.primary_font = dna.get("primary_font", "Arial")
        # --- REGISTRO EN BIBLIOTECA DE ACTIVOS (v80.0) ---
        from services.asset_library_service import register_asset
        final_library_assets = {"photos": [], "logos": [], "icons": []}
        
        raw_assets = dna.get("extracted_assets", {})
        for cat, items in raw_assets.items():
            for item in items:
                raw_path = os.path.join("uploads", item["path"])
                if os.path.exists(raw_path):
                    # Registramos en biblioteca (Deduplicación + Tagging)
                    asset_record = register_asset(db, record_dna.id, raw_path, category=cat)
                    final_library_assets[cat].append({
                        "id": asset_record.id,
                        "path": os.path.basename(asset_record.local_path),
                        "tags": asset_record.tags,
                        "description": asset_record.description
                    })
        
        record_dna.extracted_assets = final_library_assets

        # Sincronizar Legacy para que el generador actual lo vea
        legacy = db.query(models.BrandStyle).filter(models.BrandStyle.client_name == filename).first()
        if not legacy:
            legacy = models.BrandStyle(client_name=filename)
            db.add(legacy)
        legacy.primary_color = record_dna.primary_color
        legacy.secondary_color = record_dna.secondary_color
        legacy.font_family = record_dna.primary_font
        legacy.extracted_assets = record_dna.extracted_assets # Importante para el orquestador
        
        db.commit()
        print("\n✓ PROCESO COMPLETADO EXITOSAMENTE.")
        print(f"  - DNA: {len(record_dna.extracted_assets)} assets encontrados.")
        print(f"  - Essence: {len(record_ess.slide_archetypes)} arquetipos de slide detectados.")
        
    except Exception as e:
        print(f"Error guardando en DB: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    file_name = "Tesco Style_2.pptx"
    path = "uploads/brand_style_Tesco Style_2.pptx"
    reprocess(file_name, path)
