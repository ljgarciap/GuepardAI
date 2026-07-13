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


def _run_file_reorganization() -> dict:
    """
    Migra el histórico de uploads/outputs planos a la jerarquía de storage
    (Reorganización de Storage, Fase 2). Idempotente: filas ya bajo storage/
    se saltan; archivos ausentes se reportan; huérfanos NO se mueven.
    """
    import os
    from services.core import storage_service as st

    summary = {"moved": 0, "skipped": 0, "realigned": 0, "missing": 0, "conflicts": 0, "failed": 0, "orphans": 0}
    db = SessionLocal()

    def _already_in_storage(current: str, row, attr: str) -> bool:
        """Archivo ya bajo storage/ (p.ej. movido por un paso anterior como otro
        registro que apunta al mismo físico): realinear el puntero en BD igualmente."""
        if not current.startswith(os.path.abspath(st.STORAGE_ROOT)):
            return False
        rel = st.to_relative(current)
        if getattr(row, attr) != rel:
            setattr(row, attr, rel)
            summary["realigned"] += 1
        else:
            summary["skipped"] += 1
        return True

    try:
        # 1. BrandAsset → public/brands/{id}/assets
        assets = db.query(models.BrandAsset).all()
        batch = 0
        for a in assets:
            try:
                current = st.resolve(a.local_path, brand_id=a.brand_id)
                if not current:
                    summary["missing"] += 1
                    continue
                if _already_in_storage(current, a, "local_path"):
                    continue
                dest_dir = st.brand_assets_dir(a.brand_id if not a.is_public else None)
                moved = st.move_into(current, dest_dir, conflict_tag=str(a.id))
                if moved:
                    if "_dup" in os.path.basename(moved):
                        summary["conflicts"] += 1
                    a.local_path = st.to_relative(moved)
                    summary["moved"] += 1
                    batch += 1
                    if batch % 50 == 0:
                        db.commit()
            except Exception as e:
                summary["failed"] += 1
                logger.warning(f"[FileReorg] Asset {a.id} failed: {e}")
        db.commit()

        # 2. GenerationJob.pptx_path → public/jobs/{id}
        jobs = db.query(models.GenerationJob).filter(models.GenerationJob.pptx_path.isnot(None)).all()
        for j in jobs:
            try:
                current = st.resolve(j.pptx_path)
                if not current:
                    summary["missing"] += 1
                    continue
                if _already_in_storage(current, j, "pptx_path"):
                    continue
                moved = st.move_into(current, st.job_dir(j.id), conflict_tag=str(j.id))
                if moved:
                    j.pptx_path = st.to_relative(moved)
                    summary["moved"] += 1
            except Exception as e:
                summary["failed"] += 1
                logger.warning(f"[FileReorg] Job {j.id} output failed: {e}")
        db.commit()

        # 3. Brand.logo_path → public/brands/{id}/assets
        brands = db.query(models.Brand).filter(models.Brand.logo_path.isnot(None)).all()
        for b in brands:
            try:
                current = st.resolve(b.logo_path, brand_id=b.id)
                if not current:
                    summary["missing"] += 1
                    continue
                if _already_in_storage(current, b, "logo_path"):
                    continue
                moved = st.move_into(current, st.brand_assets_dir(b.id), conflict_tag=f"logo{b.id}")
                if moved:
                    b.logo_path = st.to_relative(moved)
                    summary["moved"] += 1
            except Exception as e:
                summary["failed"] += 1
                logger.warning(f"[FileReorg] Brand {b.id} logo failed: {e}")
        db.commit()

        # 4. Huérfanos en legacy (sin fila en BD): solo conteo para decisión humana
        try:
            known = set()
            for a in db.query(models.BrandAsset.local_path).all():
                if a[0]:
                    known.add(os.path.basename(a[0].replace("\\", "/")))
            if os.path.isdir(st.LEGACY_UPLOADS):
                for name in os.listdir(st.LEGACY_UPLOADS):
                    if os.path.isfile(os.path.join(st.LEGACY_UPLOADS, name)) and name not in known:
                        summary["orphans"] += 1
        except Exception as e:
            logger.warning(f"[FileReorg] Orphan scan failed: {e}")

        return summary
    finally:
        db.close()


def _run_perceptual_hash_backfill() -> dict:
    """
    Calcula el dHash perceptual para assets pre-v2 (perceptual_hash IS NULL).
    Puro PIL — no consume tokens LLM. Idempotente: re-ejecutar solo procesa
    los que siguen en NULL (archivos ausentes/corruptos se reportan y quedan
    NULL; la selección y QA toleran hashes nulos).
    Spec: docs/specs/calidad-seleccion-imagenes-v2.md
    """
    from utils.image_hash import compute_dhash
    from services.core import storage_service as st

    summary = {"processed": 0, "failed": 0, "missing": 0}
    db = SessionLocal()
    try:
        assets = db.query(models.BrandAsset).filter(
            models.BrandAsset.perceptual_hash.is_(None)
        ).all()
        batch = 0
        for a in assets:
            try:
                path = st.resolve(a.local_path, brand_id=a.brand_id) if a.local_path else None
                if not path:
                    summary["missing"] += 1
                    continue
                p_hash = compute_dhash(path)
                if p_hash:
                    a.perceptual_hash = p_hash
                    summary["processed"] += 1
                    batch += 1
                    if batch % 100 == 0:
                        db.commit()
                else:
                    summary["failed"] += 1
            except Exception as e:
                summary["failed"] += 1
                logger.warning(f"[PHashBackfill] Asset {a.id} failed: {e}")
        db.commit()
        return summary
    finally:
        db.close()


def _run_tenant_backfill() -> dict:
    """
    Crea un Tenant "legacy" por cada Brand sin tenant_id (pre-Iteración Auth).
    Idempotente: solo procesa Brand.tenant_id IS NULL.
    Spec: docs/specs/autenticacion-multiusuario-multitenant.md
    """
    summary = {"tenants_created": 0, "brands_assigned": 0, "failed": 0}
    db = SessionLocal()
    try:
        brands = db.query(models.Brand).filter(models.Brand.tenant_id.is_(None)).all()
        for brand in brands:
            try:
                tenant = models.Tenant(name=f"{brand.name} (legacy)")
                db.add(tenant)
                db.flush()  # asigna tenant.id sin cerrar la transacción
                brand.tenant_id = tenant.id
                summary["tenants_created"] += 1
                summary["brands_assigned"] += 1
            except Exception as e:
                summary["failed"] += 1
                logger.warning(f"[TenantBackfill] Brand {brand.id} failed: {e}")
        db.commit()
        return summary
    finally:
        db.close()


def _run_stale_fallback_model_fix() -> dict:
    """
    Reemplaza el último eslabón obsoleto 'claude-3-5-sonnet-20241022' de las
    cadenas de modelos por el slug OpenRouter vigente 'anthropic/claude-sonnet-4.6'.
    El id pelado cae en la rama OpenRouter de llm_provider y devuelve 400
    ('not a valid model ID') — el fallback de emergencia llevaba roto desde que
    OpenRouter retiró ese alias (detectado 2026-07-07 en test-ai-request de
    Template Merge v2 Fase 2). El seeder no re-escribe claves existentes, por
    eso esto es una alineación de datos y no un seed. Idempotente: solo toca
    filas que aún contengan el id obsoleto. No consume tokens LLM.
    """
    STALE = "claude-3-5-sonnet-20241022"
    REPLACEMENT = "anthropic/claude-sonnet-4.6"
    summary = {"updated_keys": [], "failed": 0}
    db = SessionLocal()
    try:
        rows = db.query(models.SystemConfig).filter(
            models.SystemConfig.key.in_(["extraction_synthesis_model", "global_fallback_model"]),
            models.SystemConfig.value.like(f"%{STALE}%"),
        ).all()
        for row in rows:
            try:
                row.value = row.value.replace(STALE, REPLACEMENT)
                summary["updated_keys"].append(row.key)
            except Exception as e:
                summary["failed"] += 1
                logger.warning(f"[FallbackModelFix] {row.key} failed: {e}")
        db.commit()
        return summary
    finally:
        db.close()


def _run_feedback_to_reviews() -> dict:
    """
    Migra el rating legacy de satisfacción (GenerationJobFeedback, 1 fila por
    job SIN autor) al esquema unificado de reviews (PresentationReview, 1 por
    usuario), atribuyéndolo al owner del job — según el modelo confirmado por
    Luis 2026-07-13: el rating del creador es su review individual y entra al
    promedio del team. Idempotente: si el owner ya tiene review en el job (
    orgánica o migrada, incluso borrada — no resucitar decisiones del usuario),
    se salta. Jobs sin owner_id (pre-auth) se reportan y quedan como están.
    No consume tokens LLM.
    Spec: docs/specs/reviews-analitica-colaboracion.md (unificación post-spec)
    """
    from services.core import content_moderation_service

    summary = {"migrated": 0, "skipped_existing": 0, "no_owner": 0, "failed": 0}
    db = SessionLocal()
    try:
        question = db.query(models.SurveyQuestion).filter(
            models.SurveyQuestion.key == "presentation_satisfaction"
        ).first()
        if question is None:
            return summary

        feedbacks = db.query(models.GenerationJobFeedback).filter(
            models.GenerationJobFeedback.question_id == question.id,
            models.GenerationJobFeedback.rating.isnot(None),
        ).all()
        for f in feedbacks:
            try:
                job = db.query(models.GenerationJob).get(f.job_id)
                if job is None or job.owner_id is None:
                    summary["no_owner"] += 1
                    continue
                existing = db.query(models.PresentationReview).filter(
                    models.PresentationReview.job_id == f.job_id,
                    models.PresentationReview.user_id == job.owner_id,
                ).first()
                if existing is not None:
                    summary["skipped_existing"] += 1
                    continue
                db.add(models.PresentationReview(
                    job_id=f.job_id,
                    user_id=job.owner_id,
                    rating=max(1, min(5, f.rating)),
                    comment=f.comment,
                    created_at=f.created_at,
                    moderation_status=content_moderation_service.evaluate(db, f.comment or ""),
                ))
                summary["migrated"] += 1
            except Exception as e:
                summary["failed"] += 1
                logger.warning(f"[FeedbackToReviews] Feedback {f.id} failed: {e}")
        db.commit()
        return summary
    finally:
        db.close()


ALIGNMENT_REGISTRY: Dict[str, Callable[[], dict]] = {
    "visual_profile_backfill_v1": _run_visual_profile_backfill,
    "file_reorganization_v1": _run_file_reorganization,
    "perceptual_hash_backfill_v1": _run_perceptual_hash_backfill,
    "tenant_backfill_v1": _run_tenant_backfill,
    "stale_fallback_model_fix_v1": _run_stale_fallback_model_fix,
    "feedback_to_reviews_v1": _run_feedback_to_reviews,
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
