from database import SessionLocal
from models import BrandAsset, Brand
from services.asset_library_service import register_asset
import os
import time

db = SessionLocal()
assets = db.query(BrandAsset).filter(BrandAsset.brand_id == 4).all()
print(f'Re-analyzing {len(assets)} assets for identity correction...')

for i, a in enumerate(assets):
    try:
        path = a.local_path
        old_id = a.id
        print(f'  [{i+1}/{len(assets)}] Processing ID {old_id}...')
        db.delete(a)
        db.commit()
        
        # El nombre de la marca 'Tesco' ahora está en la DB
        new_asset = register_asset(db, brand_id=4, file_path=path)
        print(f'    -> New ID {new_asset.id} | Category: {new_asset.category}')
        time.sleep(1.2)
    except Exception as e:
        print(f'  Error in ID {old_id}: {e}')
        db.rollback()

db.close()
print('RE-ANALYSIS COMPLETE')
