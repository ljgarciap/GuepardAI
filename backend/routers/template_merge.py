"""
routers/template_merge.py — Template Merge Engine endpoints.

Migrated from main.py (2026-07-07, Template Merge v2 Phase 1) per the
routers/ convention. Behavior-neutral move plus one addition: the job status
response now includes `merge_report` / `merge_summary` (v2 per-slot outcomes).

Spec: docs/specs/template-merge-v2-quality.md
Design: docs/designs/template-merge-v2-quality.md
API reference: docs/api/template-merge.md
"""
import hashlib
import os
import uuid
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

import models
from auth.dependencies import (
    check_brand_tenant_access,
    check_job_tenant_access,
    get_current_user,
    tenant_brand_ids_filter,
)
from database import get_db
from utils.sql import escape_like

router = APIRouter(prefix="/api/template-merge", tags=["Template Merge"])


class TemplateMergeRequest(BaseModel):
    template_asset_id: int
    knowledge_filename: str
    prompt: str
    brand_id: Optional[int] = None
    display_name: Optional[str] = None


class TemplateMergeRenameRequest(BaseModel):
    display_name: str


@router.post("/upload-template")
async def upload_pptx_template(
    file: UploadFile = File(...),
    brand_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Upload a PPTX file as a reusable template asset (category='pptx_template').
    The file is stored in the brand's assets directory and registered in BrandAsset.
    """
    if brand_id is not None:
        check_brand_tenant_access(db, current_user, brand_id)
    if not file.filename or not file.filename.lower().endswith(".pptx"):
        raise HTTPException(status_code=400, detail="Only .pptx files are accepted as templates.")

    from services.core.storage_service import brand_assets_dir, to_relative

    dest_dir = brand_assets_dir(brand_id or "_templates")
    safe_name = f"tpl_{uuid.uuid4().hex[:8]}_{file.filename}"
    dest_path = os.path.join(dest_dir, safe_name)

    content = await file.read()
    with open(dest_path, "wb") as f:
        f.write(content)

    file_hash = hashlib.sha256(content).hexdigest()

    asset = models.BrandAsset(
        brand_id=brand_id,
        file_hash=file_hash,
        local_path=to_relative(dest_path),
        category="pptx_template",
        tags=[],
        manual_tags=[],
        description=f"PPTX template: {file.filename}",
        source_doc=file.filename,
        is_public=0,
        metadata_json={"original_filename": file.filename},
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    return {
        "asset_id": asset.id,
        "filename": file.filename,
        "stored_as": safe_name,
        "category": "pptx_template",
    }


@router.post("/jobs")
def create_template_merge_job(
    req: TemplateMergeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Create and enqueue a Template Merge job.
    The template (a BrandAsset with category='pptx_template') and an already-
    ingested knowledge filename are combined to generate a new PPTX.
    """
    if req.brand_id is not None:
        check_brand_tenant_access(db, current_user, req.brand_id)
    from tasks import celery_run_template_merge

    asset = db.query(models.BrandAsset).filter(
        models.BrandAsset.id == req.template_asset_id,
        models.BrandAsset.category == "pptx_template",
    ).first()
    if not asset:
        raise HTTPException(
            status_code=404,
            detail=f"Template asset {req.template_asset_id} not found or not a pptx_template.",
        )
    if asset.brand_id is not None:
        # El template puede pertenecer a un brand distinto del job (ej. un
        # template compartido) — igual debe validarse contra el tenant.
        check_brand_tenant_access(db, current_user, asset.brand_id)

    job = models.TemplateMergeJob(
        brand_id=req.brand_id,
        template_asset_id=req.template_asset_id,
        knowledge_filename=req.knowledge_filename,
        prompt=req.prompt,
        display_name=req.display_name,
        status="pending",
        progress=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    celery_run_template_merge.delay(job.id)

    return {
        "job_id": job.id,
        "status": job.status,
        "message": "Template merge job enqueued.",
    }


@router.get("/jobs")
def list_template_merge_jobs(
    brand_id: Optional[int] = None,
    search: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = 1,
    page_size: int = 12,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Lista paginada de Template Merge jobs completados (más reciente primero)."""
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be earlier than or equal to date_to.")

    if brand_id:
        check_brand_tenant_access(db, current_user, brand_id)

    query = db.query(models.TemplateMergeJob).filter(models.TemplateMergeJob.status == "completed")
    if brand_id:
        query = query.filter(models.TemplateMergeJob.brand_id == brand_id)
    else:
        tenant_ids = tenant_brand_ids_filter(db, current_user)
        if tenant_ids is not None:
            query = query.filter(models.TemplateMergeJob.brand_id.in_(tenant_ids))
    if search and search.strip():
        pattern = f"%{escape_like(search.strip())}%"
        query = query.filter(or_(
            models.TemplateMergeJob.display_name.ilike(pattern, escape="\\"),
            models.TemplateMergeJob.output_path.ilike(pattern, escape="\\"),
        ))
    if date_from:
        query = query.filter(models.TemplateMergeJob.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(models.TemplateMergeJob.created_at <= datetime.combine(date_to, datetime.max.time()))

    total = query.count()
    jobs = (query.order_by(models.TemplateMergeJob.created_at.desc())
                 .offset((page - 1) * page_size)
                 .limit(page_size)
                 .all())

    items = [{
        "id": j.id,
        "filename": os.path.basename(j.output_path) if j.output_path else f"Merge_{j.id}.pptx",
        "display_name": _template_merge_display_name(j),
        "created_at": j.created_at,
        "brand_id": j.brand_id,
    } for j in jobs]

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/jobs/{job_id}")
def get_template_merge_job_status(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Poll status, progress and current step of a Template Merge job."""
    job = db.query(models.TemplateMergeJob).get(job_id)
    check_job_tenant_access(db, current_user, job)

    from services.core.storage_service import public_url, resolve as resolve_storage
    output_url = None
    if job.output_path:
        physical = resolve_storage(job.output_path)
        if physical:
            url = public_url(physical)
            output_url = url.lstrip("/") if url else None

    return {
        "job_id": job.id,
        "status": job.status,
        "progress": job.progress,
        "current_step": job.current_step,
        "error_detail": job.error_detail,
        "output_url": output_url,
        "display_name": job.display_name,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "merge_report": job.merge_report,
        "merge_summary": (job.merge_report or {}).get("summary"),
    }


@router.get("/jobs/{job_id}/download")
def download_template_merge_result(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Download the merged PPTX once the job is completed."""
    job = db.query(models.TemplateMergeJob).get(job_id)
    check_job_tenant_access(db, current_user, job)
    if job.status != "completed":
        raise HTTPException(status_code=409, detail=f"Job is not completed yet (status={job.status}).")
    if not job.output_path:
        raise HTTPException(status_code=500, detail="Job completed but output path is missing.")

    from services.core.storage_service import resolve as resolve_storage
    physical = resolve_storage(job.output_path)
    if not physical or not os.path.isfile(physical):
        raise HTTPException(status_code=404, detail="Output file not found on disk.")

    filename = job.display_name or os.path.basename(physical)
    if not filename.endswith(".pptx"):
        filename = os.path.basename(physical)

    return FileResponse(
        path=physical,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=filename,
    )


@router.patch("/jobs/{job_id}")
def rename_template_merge_job(
    job_id: int,
    payload: TemplateMergeRenameRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Renombra la etiqueta visible de un Template Merge job (no toca el archivo físico)."""
    job = db.query(models.TemplateMergeJob).get(job_id)
    check_job_tenant_access(db, current_user, job)

    name = (payload.display_name or "").strip()
    if not name or len(name) > 120:
        raise HTTPException(status_code=422, detail="display_name must be between 1 and 120 characters.")

    job.display_name = name
    db.commit()
    return {"id": job.id, "display_name": job.display_name,
            "filename": os.path.basename(job.output_path) if job.output_path else f"Merge_{job.id}.pptx"}


@router.delete("/jobs/{job_id}")
def delete_template_merge_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Elimina un Template Merge job + su archivo físico (tolerante). Solo estados terminales."""
    job = db.query(models.TemplateMergeJob).get(job_id)
    check_job_tenant_access(db, current_user, job)
    if job.status not in ["completed", "error"]:
        raise HTTPException(status_code=409, detail=f"Cannot delete a job while its pipeline is active (status: {job.status}).")

    output_path = job.output_path
    db.delete(job)
    db.commit()

    if output_path:
        try:
            from services.core.storage_service import resolve as resolve_storage
            physical = resolve_storage(output_path)
            if physical and os.path.exists(physical):
                os.remove(physical)
        except Exception:
            pass

    return {"deleted": True, "id": job_id}


@router.get("/templates")
def list_template_assets(
    brand_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """List all uploaded PPTX templates (category='pptx_template')."""
    if brand_id is not None:
        check_brand_tenant_access(db, current_user, brand_id)

    q = db.query(models.BrandAsset).filter(models.BrandAsset.category == "pptx_template")
    if brand_id is not None:
        q = q.filter(models.BrandAsset.brand_id == brand_id)

    items = []
    for asset in q.order_by(models.BrandAsset.created_at.desc()).all():
        items.append({
            "id": asset.id,
            "filename": asset.source_doc or os.path.basename(asset.local_path or ""),
            "description": asset.description,
            "brand_id": asset.brand_id,
            "created_at": asset.created_at.isoformat() if asset.created_at else None,
        })
    return items


def _template_merge_display_name(job) -> str:
    """Nombre visible: etiqueta editable > basename del output > fallback."""
    if job.display_name:
        return job.display_name
    if job.output_path:
        return os.path.basename(job.output_path)
    return f"Merge_{job.id}.pptx"
