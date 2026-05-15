
import os
from database import SessionLocal
import models
from services.asset_library_service import register_asset
from llm_provider import generate_vision_json, get_embedding

def reanalyze_library():
    db = SessionLocal()
    try:
        # 1. Obtener el nuevo prompt de la DB
        config = db.query(models.SystemConfig).filter(models.SystemConfig.key == "prompt_classifier_v1").first()
        vision_prompt = config.value if config else "Analyze this image technicaly."
        
        print(f"  [Re-Analysis] Using Prompt: {vision_prompt[:100]}...")

        # 2. Obtener todos los assets ordenados por ID
        assets = db.query(models.BrandAsset).order_by(models.BrandAsset.id).all()
        print(f"  [Re-Analysis] Found {len(assets)} assets to re-analyze.")

        for asset in assets:
            if not asset.local_path or not os.path.exists(asset.local_path):
                print(f"  [Skip] Path not found: {asset.local_path}")
                continue

            print(f"  [Processing] ID #{asset.id} - {os.path.basename(asset.local_path)}")
            
            try:
                # Re-ejecutar Visión
                vision_res = generate_vision_json(vision_prompt, [asset.local_path])
                
                new_desc = vision_res.get("description", asset.description)
                new_tags = vision_res.get("tags", asset.tags)
                new_cat = vision_res.get("category", asset.category).lower()
                
                # Actualizar DB
                asset.description = new_desc
                asset.tags = new_tags
                asset.category = new_cat
                
                # Re-generar embedding del texto
                asset.embedding = get_embedding(new_desc)
                
                print(f"    [Success] New Desc: {new_desc[:50]}...")
                db.commit()
            except Exception as e:
                print(f"    [Error] Failed to re-analyze ID #{asset.id}: {e}")
                db.rollback()

        print("\n  [Done] Library re-analyzed with Designer Rigor.")

    finally:
        db.close()

if __name__ == "__main__":
    reanalyze_library()
