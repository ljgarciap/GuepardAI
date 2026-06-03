import os
import sys

# Ensure the backend directory is in the Python search path for Celery workers
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from celery import Celery

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
