from database import SessionLocal
import models

db = SessionLocal()
try:
    jobs = db.query(models.IngestionJob).filter(models.IngestionJob.status == 'processing').all()
    if not jobs:
        print("No hay procesos de ingesta en curso (status='processing').")
    else:
        for job in jobs:
            print(f"Job ID: {job.id}")
            print(f"Tipo: {job.ingestion_type}")
            print(f"Archivo: {job.client_name}")
            print(f"Progreso: {job.progress}%")
            print(f"Paso actual: {job.current_step}")
            print(f"Last update: {job.updated_at}")
            print("-" * 20)
finally:
    db.close()
