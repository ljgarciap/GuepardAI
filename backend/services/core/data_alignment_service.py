"""
data_alignment_service.py — Alineaciones de Datos Automáticas en el Arranque.

La tercera capa de alineación post-deploy, junto al esquema (ALTERs idempotentes
en database.py) y la configuración (seed.py). Cada alineación es una función
idempotente con nombre versionado; el arranque del API detecta las pendientes y
las encola como tareas Celery sin bloquear nunca el boot.

CONTRATO PARA REGISTRAR UNA ALINEACIÓN NUEVA:
  1. La función NO recibe argumentos y devuelve un dict-resumen serializable
     (ej. {"processed": 10, "failed": 0}).
  2. DEBE ser idempotente: re-ejecutarla sobre datos ya alineados converge a
     cero trabajo. Es requisito, no sugerencia — los estados `failed` se
     reintentan automáticamente en el siguiente arranque.
  3. El nombre lleva sufijo de versión (`_v1`, `_v2`...). Nunca reutilizar un
     nombre ya marcado `done` para lógica distinta: registrar una versión nueva.

Spec: docs/specs/alineaciones-de-datos.md
Design: docs/designs/alineaciones-de-datos.md
"""
import datetime
import json
import logging
import time
from typing import Callable, Dict

from database import SessionLocal
import models

logger = logging.getLogger(__name__)

DETAIL_MAX_CHARS = 2000


# ─────────────────────────────────────────────────────────────────────────────
# ALINEACIONES REGISTRADAS
# ─────────────────────────────────────────────────────────────────────────────
def _run_visual_profile_backfill() -> dict:
    """Perfila assets pre-Iteración-1 (visual_profile IS NULL, todas las marcas)."""
    from utils.backfill_visual_profiles import backfill
    return backfill(process_all=True)


ALIGNMENT_REGISTRY: Dict[str, Callable[[], dict]] = {
    "visual_profile_backfill_v1": _run_visual_profile_backfill,
}


# ─────────────────────────────────────────────────────────────────────────────
# DISPATCH (llamado desde el arranque del API — jamás debe bloquear el boot)
# ─────────────────────────────────────────────────────────────────────────────
def _is_auto_enabled(db) -> bool:
    cfg = db.query(models.SystemConfig).filter(
        models.SystemConfig.key == "auto_data_alignment_enabled"
    ).first()
    return (cfg.value if cfg else "true").strip().lower() == "true"


def dispatch_pending_alignments() -> dict:
    """
    Asegura una fila por alineación registrada y encola las pendientes/fallidas.
    Cualquier error individual (Redis caído, etc.) se loggea y se continúa.
    """
    summary = {"enqueued": [], "skipped": [], "disabled": False, "orphans": []}
    db = SessionLocal()
    try:
        auto_enabled = _is_auto_enabled(db)
        summary["disabled"] = not auto_enabled

        # Alineaciones huérfanas: filas de versiones anteriores ya no registradas
        known_names = list(ALIGNMENT_REGISTRY.keys())
        orphans = db.query(models.DataAlignment).filter(
            models.DataAlignment.name.notin_(known_names)
        ).all()
        for o in orphans:
            summary["orphans"].append(o.name)
            logger.info(f"[Alignments] Ignoring orphan alignment '{o.name}' (status={o.status}) — not in registry.")

        for name in known_names:
            rec = db.query(models.DataAlignment).filter(
                models.DataAlignment.name == name
            ).first()
            if not rec:
                rec = models.DataAlignment(name=name, status="pending")
                db.add(rec)
                db.commit()

            if rec.status in ("done", "running"):
                summary["skipped"].append({"name": name, "status": rec.status})
                continue

            if not auto_enabled:
                logger.warning(f"[Alignments] Pending alignment '{name}' NOT enqueued (auto_data_alignment_enabled=false).")
                summary["skipped"].append({"name": name, "status": rec.status, "reason": "auto disabled"})
                continue

            try:
                from tasks import task_run_data_alignment
                task_run_data_alignment.delay(name)
                logger.info(f"[Alignments] Enqueued data alignment: {name}")
                summary["enqueued"].append(name)
            except Exception as enqueue_err:
                logger.warning(f"[Alignments] Enqueue failed for '{name}' (will retry next boot): {enqueue_err}")
                summary["skipped"].append({"name": name, "status": rec.status, "reason": str(enqueue_err)[:200]})
        return summary
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# EJECUCIÓN (corre dentro del worker Celery)
# ─────────────────────────────────────────────────────────────────────────────
def run_alignment(name: str) -> dict:
    """
    Ejecuta una alineación con claim atómico: el UPDATE condicional garantiza
    que solo una réplica/tarea la ejecute aunque se haya encolado dos veces.
    """
    from utils.observability import log_performance_metric

    db = SessionLocal()
    start_time = time.perf_counter()
    try:
        claimed = db.query(models.DataAlignment).filter(
            models.DataAlignment.name == name,
            models.DataAlignment.status.in_(["pending", "failed"]),
        ).update(
            {"status": "running", "started_at": datetime.datetime.utcnow()},
            synchronize_session=False,
        )
        db.commit()
        if not claimed:
            logger.info(f"[Alignments] '{name}' not claimable (already running/done or unknown row). Skipping.")
            return {"name": name, "skipped": True}

        runner = ALIGNMENT_REGISTRY.get(name)
        if not runner:
            _finish(db, name, "failed", f"Alignment '{name}' is not in the registry (orphan from a previous version).")
            return {"name": name, "status": "failed", "reason": "not registered"}

        try:
            result = runner() or {}
            detail = json.dumps(result)[:DETAIL_MAX_CHARS]
            _finish(db, name, "done", detail)
            log_performance_metric(
                event_name=f"data_alignment.{name}.complete",
                duration=time.perf_counter() - start_time,
                metadata={"name": name, "result": result},
            )
            logger.info(f"[Alignments] '{name}' DONE: {detail}")
            return {"name": name, "status": "done", "result": result}
        except Exception as run_err:
            _finish(db, name, "failed", str(run_err)[:DETAIL_MAX_CHARS])
            log_performance_metric(
                event_name=f"data_alignment.{name}.failed",
                duration=time.perf_counter() - start_time,
                metadata={"name": name, "error": str(run_err)[:500]},
            )
            logger.error(f"[Alignments] '{name}' FAILED (will retry next boot): {run_err}")
            return {"name": name, "status": "failed", "error": str(run_err)[:500]}
    finally:
        db.close()


def _finish(db, name: str, status: str, detail: str):
    db.query(models.DataAlignment).filter(models.DataAlignment.name == name).update(
        {"status": status, "detail": detail, "finished_at": datetime.datetime.utcnow()},
        synchronize_session=False,
    )
    db.commit()
