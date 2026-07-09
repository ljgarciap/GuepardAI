"""
routers/collaborators.py — Colaboradores de un GenerationJob (además del owner).

Spec: docs/specs/reviews-analitica-colaboracion.md
Design: docs/designs/reviews-analitica-colaboracion.md §1
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

import models
from auth.dependencies import check_job_tenant_access, get_current_user
from database import get_db

router = APIRouter(prefix="/api/presentations", tags=["Collaboration"])


class CollaboratorRequest(BaseModel):
    user_id: int


def _require_job_owner_or_tenant_admin(db: Session, current_user: models.User, job: models.GenerationJob) -> None:
    """Puerta de escritura sobre colaboradores: owner del job, admin del tenant, o superadmin."""
    if current_user.role == models.UserRole.SUPERADMIN.value:
        return
    if job.owner_id == current_user.id:
        return
    if current_user.role == models.UserRole.ADMIN.value:
        brand = db.query(models.Brand).filter(models.Brand.id == job.brand_id).first() if job.brand_id else None
        if brand is not None and brand.tenant_id == current_user.tenant_id:
            return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the job owner or a tenant admin can manage collaborators")


@router.post("/{job_id}/collaborators")
def add_collaborator(job_id: int, request: CollaboratorRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Agrega un colaborador al job. Solo el owner o un admin del tenant."""
    job = db.query(models.GenerationJob).get(job_id)
    check_job_tenant_access(db, current_user, job)
    _require_job_owner_or_tenant_admin(db, current_user, job)

    target_user = db.query(models.User).filter(models.User.id == request.user_id).first()
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    brand = db.query(models.Brand).filter(models.Brand.id == job.brand_id).first() if job.brand_id else None
    if brand is None or brand.tenant_id is None or target_user.tenant_id != brand.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User belongs to a different tenant")

    existing = db.query(models.GenerationJobCollaborator).filter(
        models.GenerationJobCollaborator.job_id == job_id,
        models.GenerationJobCollaborator.user_id == request.user_id,
    ).first()
    if existing:
        return {"user_id": existing.user_id, "added_at": existing.added_at}

    collaborator = models.GenerationJobCollaborator(job_id=job_id, user_id=request.user_id)
    db.add(collaborator)
    db.commit()
    db.refresh(collaborator)
    return {"user_id": collaborator.user_id, "added_at": collaborator.added_at}


@router.delete("/{job_id}/collaborators/{user_id}")
def remove_collaborator(job_id: int, user_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Quita un colaborador del job. Solo el owner o un admin del tenant."""
    job = db.query(models.GenerationJob).get(job_id)
    check_job_tenant_access(db, current_user, job)
    _require_job_owner_or_tenant_admin(db, current_user, job)

    collaborator = db.query(models.GenerationJobCollaborator).filter(
        models.GenerationJobCollaborator.job_id == job_id,
        models.GenerationJobCollaborator.user_id == user_id,
    ).first()
    if collaborator is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collaborator not found")
    db.delete(collaborator)
    db.commit()
    return {"status": "removed"}


@router.get("/{job_id}/collaborators")
def list_collaborators(job_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Lista colaboradores. Cualquier owner/colaborador/admin del tenant del job puede ver."""
    job = db.query(models.GenerationJob).get(job_id)
    check_job_tenant_access(db, current_user, job)
    collaborators = db.query(models.GenerationJobCollaborator).options(
        joinedload(models.GenerationJobCollaborator.user)
    ).filter(
        models.GenerationJobCollaborator.job_id == job_id
    ).all()
    return [
        {"user_id": c.user_id, "email": c.user.email, "added_at": c.added_at}
        for c in collaborators
    ]
