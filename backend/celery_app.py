import os
import sys
from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "guepard_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Habilitar modo síncrono si estamos corriendo pruebas unitarias/integración
    task_always_eager="pytest" in sys.modules,
    # Importar explícitamente el archivo de tareas para que el worker las registre
    imports=["tasks"]
)

# Tareas periódicas (requiere el servicio `celery_beat` corriendo — ver
# docker-compose.yml; sin él, `beat_schedule` nunca dispara, sin error visible).
celery_app.conf.beat_schedule = {
    "monthly-usage-report": {
        "task": "tasks.generate_monthly_usage_report",
        "schedule": crontab(day_of_month=1, hour=6, minute=0),
    },
}
