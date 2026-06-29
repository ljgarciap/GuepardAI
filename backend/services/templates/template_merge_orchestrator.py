"""
template_merge_orchestrator.py — Pipeline runner for the Template Merge Engine.

Called by the Celery task (tasks.py). Owns the job lifecycle:
  PENDING → PROCESSING → (per-step progress) → COMPLETED | ERROR
"""
import logging
import os
import uuid
from datetime import datetime

from database import SessionLocal
import models
from services.core.storage_service import job_dir, to_relative, resolve as resolve_storage
from services.templates.template_analyzer import analyze_template
from services.templates.template_content import generate_slide_contents
from services.templates.template_renderer import render_merged_pptx

logger = logging.getLogger(__name__)


def run_template_merge(job_id: int) -> None:
    """
    Full pipeline for a TemplateMergeJob.  Never raises — all failures are
    caught and persisted into the job's error_detail column.
    """
    db = SessionLocal()
    try:
        job = db.query(models.TemplateMergeJob).get(job_id)
        if not job:
            logger.error(f"[TemplateMerge] Job {job_id} not found.")
            return

        _set_status(db, job, "processing", "Starting template merge pipeline...", 5)

        # ── Step 1: resolve template file path ─────────────────────────────
        template_asset = db.query(models.BrandAsset).get(job.template_asset_id)
        if not template_asset:
            raise ValueError(f"Template asset {job.template_asset_id} not found.")

        template_path = resolve_storage(template_asset.local_path, brand_id=job.brand_id)
        if not template_path or not os.path.isfile(template_path):
            raise FileNotFoundError(
                f"Template file not found on disk: {template_asset.local_path}"
            )

        _set_status(db, job, "processing", "Analyzing template structure...", 15)

        # ── Step 2: analyze template ────────────────────────────────────────
        profiles = analyze_template(template_path)
        logger.info(f"[TemplateMerge] Job {job_id}: {len(profiles)} slides analyzed.")

        _set_status(db, job, "processing", "Generating slide content from knowledge base...", 35)

        # ── Step 3: generate content per slide ─────────────────────────────
        slide_contents = generate_slide_contents(
            profiles=profiles,
            knowledge_filename=job.knowledge_filename,
            brand_id=job.brand_id or 0,
            user_prompt=job.prompt,
        )

        _set_status(db, job, "processing", "Assembling final presentation...", 75)

        # ── Step 4: render merged PPTX ─────────────────────────────────────
        out_dir = job_dir(f"tm_{job_id}")
        template_basename = os.path.basename(template_asset.local_path or "output.pptx")
        stem, _ = os.path.splitext(template_basename)
        output_filename = f"{stem}_merged_{uuid.uuid4().hex[:6]}.pptx"
        output_path = os.path.join(out_dir, output_filename)

        render_merged_pptx(
            template_path=template_path,
            profiles=profiles,
            slide_contents=slide_contents,
            output_path=output_path,
        )

        # ── Step 5: persist result ──────────────────────────────────────────
        job.output_path = to_relative(output_path)
        job.display_name = job.display_name or f"{stem} (merged)"
        _set_status(db, job, "completed", "Done.", 100)
        logger.info(f"[TemplateMerge] Job {job_id} completed → {output_path}")

    except Exception as exc:
        logger.exception(f"[TemplateMerge] Job {job_id} failed: {exc}")
        db2 = SessionLocal()
        try:
            j = db2.query(models.TemplateMergeJob).get(job_id)
            if j:
                j.status = "error"
                j.error_detail = str(exc)
                j.updated_at = datetime.utcnow()
                db2.commit()
        finally:
            db2.close()
    finally:
        db.close()


def _set_status(db, job, status: str, step: str, progress: int) -> None:
    job.status = status
    job.current_step = step
    job.progress = progress
    job.updated_at = datetime.utcnow()
    db.commit()
