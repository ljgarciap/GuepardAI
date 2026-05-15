from database import SessionLocal
from services.asset_library_service import register_asset
import os
import time

db = SessionLocal()
upload_dir = '/app/uploads'
# Solo procesamos los que empiezan por img_
files = sorted([f for f in os.listdir(upload_dir) if f.startswith('img_')])
print(f'Recovering {len(files)} files with IMMEDIATE COMMIT...')

for i, filename in enumerate(files):
    path = os.path.join(upload_dir, filename)
    try:
        print(f'  [{i+1}/{len(files)}] Registering: {filename}...')
        # Re-registramos a la marca 4 (Tesco)
        new_asset = register_asset(db, brand_id=4, file_path=path)
        db.commit() # <--- LA CLAVE: Guardar inmediatamente
        print(f'    -> SAVED: ID {new_asset.id} | Category: {new_asset.category}')
        time.sleep(0.5) # Más rápido ahora que ya tenemos caché de visión
    except Exception as e:
        print(f'  Error in {filename}: {e}')
        db.rollback()

db.close()
print('RECOVERY FINISHED')
