from database import SessionLocal
from models import BrandAsset
from llm_provider import get_embedding
import time

db = SessionLocal()
assets = db.query(BrandAsset).all()
print(f'Smart Re-indexing {len(assets)} assets...')

for i, a in enumerate(assets):
    if not a.description:
        continue
    try:
        print(f'  [{i+1}/{len(assets)}] Indexing ID {a.id}...')
        emb = get_embedding(a.description)
        if emb:
            a.embedding = emb
            db.commit()
            time.sleep(1.2)
        else:
            print(f'  [Warning] No embedding for ID {a.id}')
    except Exception as e:
        print(f'  [Error] ID {a.id}: {e}')
        db.rollback()

db.close()
print('RE-INDEXING FINISHED')
