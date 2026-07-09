"""
routers/portfolios.py — Detalle de un job de la biblioteca para "Usar como
base" (soporte-indicaciones). El listado/rename/delete de portfolios siguen
en main.py (legacy) — solo las rutas nuevas van acá.

Spec: docs/specs/soporte-indicaciones.md
Design: docs/designs/soporte-indicaciones.md
"""
import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import models
from auth.dependencies import check_job_tenant_access, get_current_user
from database import get_db
from services.core.portfolio_service import portfolio_display_name

router = APIRouter(prefix="/api/library/portfolios", tags=["Library"])


@router.get("/{job_id}")
def get_library_portfolio_detail(job_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Detalle de un job para 'Usar como base': incluye prompt y prompt_metadata.
    404 si el job no existe o no tiene prompt (nada que reusar)."""
    job = db.query(models.GenerationJob).get(job_id)
    check_job_tenant_access(db, current_user, job)
    if not job.prompt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job has no reusable prompt")

    return {
        "id": job.id,
        "filename": os.path.basename(job.pptx_path) if job.pptx_path else f"Presentation_{job.id}.pptx",
        "display_name": portfolio_display_name(job),
        "created_at": job.created_at,
        "brand_id": job.brand_id,
        "prompt": job.prompt,
        "prompt_metadata": job.prompt_metadata,
    }
