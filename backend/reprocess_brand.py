import os
import json
from dotenv import load_dotenv
from services.visual_dna_service import extract_visual_dna
from services.artistic_essence_service import extract_artistic_essence
from database import SessionLocal
import models

load_dotenv()

def reprocess(filename, source_path):
    print(f"--- Reprocessing: {filename} ---")
    
    # 1. Extract Visual DNA
    print("1/2 Extracting Visual DNA (Colors, Fonts)...")
    dna = extract_visual_dna(source_path, "uploads")
    
    # 2. Extract Artistic Essence (Vision LLM)
    print("2/2 Analyzing Artistic Essence (Vision LLM with Gemini/Claude)...")
    essence = extract_artistic_essence(source_path, "uploads")
    
    # 3. Persist in DB
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

        # Atomic Asset Registration
        from services.asset_library_service import register_asset
        final_library_assets = {"photos": [], "logos": [], "icons": []}
        
        raw_assets = dna.get("extracted_assets", {})
        for cat, items in raw_assets.items():
            for item in items:
                raw_path = os.path.join("uploads", item["path"])
                if os.path.exists(raw_path):
                    asset_record = register_asset(db, record_dna.id, raw_path, category=cat)
                    final_library_assets[cat].append({
                        "id": asset_record.id,
                        "path": os.path.basename(asset_record.local_path),
                        "tags": asset_record.tags,
                        "description": asset_record.description
                    })
        
        record_dna.extracted_assets = final_library_assets
        db.commit()
        print("\n✓ PROCESS COMPLETED SUCCESSFULLY.")
        
    except Exception as e:
        print(f"Error saving to DB: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    file_name = "Tesco Style_2.pptx"
    path = "uploads/brand_style_Tesco Style_2.pptx"
    reprocess(file_name, path)
