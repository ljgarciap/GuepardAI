import os
import shutil
from database import SessionLocal, engine
import models

def clean_environment():
    db = SessionLocal()
    try:
        print("[Cleaner] Cleaning database tables...", flush=True)
        # Limpieza en orden de dependencia
        db.query(models.PresentationSlide).delete()
        db.query(models.GenerationJob).delete()
        db.query(models.CorporateKnowledge).delete()
        db.query(models.BrandAsset).delete()
        db.query(models.BrandArtisticEssence).delete()
        db.query(models.BrandVisualDna).delete()
        db.query(models.Brand).delete()
        db.commit()
        print("[Cleaner] Database: Brand data, jobs and assets cleared.")

        print("[Cleaner] Cleaning uploads directory...", flush=True)
        uploads_dir = "uploads"
        if os.path.exists(uploads_dir):
            for filename in os.listdir(uploads_dir):
                file_path = os.path.join(uploads_dir, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    print(f'Failed to delete {file_path}. Reason: {e}')
        print("[Cleaner] Uploads: Directory emptied.")

    except Exception as e:
        db.rollback()
        print(f"[Cleaner] Error during cleaning: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    clean_environment()
