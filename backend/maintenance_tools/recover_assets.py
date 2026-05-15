from database import SessionLocal
from services.asset_library_service import register_asset
import os
import time

db = SessionLocal()
upload_dir = '/app/uploads'
files = [f for f in os.listdir(upload_dir) if f.startswith('img_')]
print(f'Recovering and Re-indexing {len(files)} files from {upload_dir}...')

for i, filename in enumerate(files):
    path = os.path.join(upload_dir, filename)
    try:
        print(f'  [{i+1}/{len(files)}] Registering: {filename}...')
        # Re-registramos todo a la marca 4 (Tesco)
        # El sistema detectará automáticamente si es logo, foto o elemento
        new_asset = register_asset(db, brand_id=4, file_path=path)
        print(f'    -> Success: ID {new_asset.id} | Category: {new_asset.category}')
        time.sleep(1.2)
    except Exception as e:
        print(f'  Error in {filename}: {e}')

db.close()
print('RECOVERY COMPLETE')
