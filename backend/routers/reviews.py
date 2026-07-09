"""
routers/reviews.py — Reviews/ratings sobre un GenerationJob + moderación
(filtro de palabras, sin LLM).

Spec: docs/specs/reviews-analitica-colaboracion.md
Design: docs/designs/reviews-analitica-colaboracion.md §2-3
"""
import calendar
import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, contains_eager, joinedload

import models
from auth.dependencies import check_job_tenant_access, get_current_user, require_role
from database import get_db
from services.core import content_moderation_service
from services.core.portfolio_service import portfolio_display_name

router = APIRouter(tags=["Reviews"])


class ReviewRequest(BaseModel):
    rating: int
    comment: Optional[str] = None


class ModerationUpdateRequest(BaseModel):
    status: str  # 'visible' | 'hidden'


class BlocklistUpdateRequest(BaseModel):
    terms: List[str]


def _add_months(dt: datetime, months: int) -> datetime:
    """Suma `months` meses calendario a `dt` (sin dependencia nueva de dateutil)."""
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _require_review_window_open(job: models.GenerationJob) -> None:
    """Ventana de edición: 6 meses desde la CREACIÓN del job (no de la review)."""
    deadline = _add_months(job.created_at, 6)
    if datetime.utcnow() > deadline:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Review window closed (6 months after job creation)")


def _require_owner_or_collaborator(db: Session, current_user: models.User, job: models.GenerationJob) -> None:
    if current_user.role == models.UserRole.SUPERADMIN.value:
        return
    if job.owner_id == current_user.id:
        return
    is_collaborator = db.query(models.GenerationJobCollaborator).filter(
        models.GenerationJobCollaborator.job_id == job.id,
        models.GenerationJobCollaborator.user_id == current_user.id,
    ).first() is not None
    if is_collaborator:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the job owner or a collaborator can review this presentation")


def _serialize_review(r: models.PresentationReview) -> dict:
    return {
        "id": r.id,
        "job_id": r.job_id,
        "user_id": r.user_id,
        "user_email": r.user.email if r.user else None,
        "rating": r.rating,
        "comment": r.comment,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
        "moderation_status": r.moderation_status,
    }


@router.post("/api/presentations/{job_id}/reviews")
def upsert_review(job_id: int, request: ReviewRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Crea o actualiza (upsert) la review propia sobre un job. Ventana: 6 meses desde la creación del job."""
    if not (1 <= request.rating <= 5):
        raise HTTPException(status_code=422, detail="rating must be between 1 and 5")

    job = db.query(models.GenerationJob).get(job_id)
    check_job_tenant_access(db, current_user, job)
    _require_owner_or_collaborator(db, current_user, job)
    _require_review_window_open(job)

    moderation_status = content_moderation_service.evaluate(db, request.comment or "")

    review = db.query(models.PresentationReview).filter(
        models.PresentationReview.job_id == job_id,
        models.PresentationReview.user_id == current_user.id,
    ).first()
    if review is None:
        review = models.PresentationReview(job_id=job_id, user_id=current_user.id)
        db.add(review)
    review.rating = request.rating
    review.comment = request.comment
    review.is_deleted = False
    review.moderation_status = moderation_status
    db.commit()
    db.refresh(review)
    return _serialize_review(review)


@router.delete("/api/presentations/{job_id}/reviews/me")
def delete_own_review(job_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Soft-delete de la review propia. Misma ventana de 6 meses que la edición."""
    job = db.query(models.GenerationJob).get(job_id)
    check_job_tenant_access(db, current_user, job)
    _require_review_window_open(job)

    review = db.query(models.PresentationReview).filter(
        models.PresentationReview.job_id == job_id,
        models.PresentationReview.user_id == current_user.id,
    ).first()
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    review.is_deleted = True
    db.commit()
    return {"status": "deleted"}


@router.get("/api/presentations/{job_id}/reviews")
def list_reviews(job_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Lista reviews visibles. Admin/superadmin del tenant también ven flagged/hidden."""
    job = db.query(models.GenerationJob).get(job_id)
    check_job_tenant_access(db, current_user, job)

    query = db.query(models.PresentationReview).options(joinedload(models.PresentationReview.user)).filter(
        models.PresentationReview.job_id == job_id,
        models.PresentationReview.is_deleted == False,
    )
    is_admin = current_user.role in (models.UserRole.ADMIN.value, models.UserRole.SUPERADMIN.value)
    if not is_admin:
        # 'flagged' es un auto-tag pendiente de revisión, no un ocultamiento — solo
        # 'hidden' (acción explícita de un admin) saca una review de la vista normal.
        query = query.filter(models.PresentationReview.moderation_status != "hidden")

    reviews = query.order_by(models.PresentationReview.created_at.desc()).all()
    counted = [r for r in reviews if r.moderation_status != "hidden"]
    rating_average = round(sum(r.rating for r in counted) / len(counted), 2) if counted else None
    return {
        "reviews": [_serialize_review(r) for r in reviews],
        "rating_average": rating_average,
        "rating_count": len(counted),
    }


@router.get("/api/admin/reviews")
def list_admin_reviews(
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(models.UserRole.ADMIN.value, models.UserRole.SUPERADMIN.value)),
):
    """Listado de reviews para moderación — admin ve solo su tenant, superadmin ve todo.
    `status_filter`: 'visible' | 'flagged' | 'hidden' (omitir = todos, no deleted)."""
    if status_filter is not None and status_filter not in ("visible", "flagged", "hidden"):
        raise HTTPException(status_code=422, detail="status_filter must be 'visible', 'flagged' or 'hidden'")

    # contains_eager (no joinedload) para .job: la tabla ya se joinea para el filtro de
    # tenant de abajo — un joinedload aparte duplicaría el join en vez de reusarlo.
    query = db.query(models.PresentationReview).options(
        joinedload(models.PresentationReview.user), contains_eager(models.PresentationReview.job)
    ).join(
        models.GenerationJob, models.GenerationJob.id == models.PresentationReview.job_id
    ).filter(models.PresentationReview.is_deleted == False)

    if current_user.role != models.UserRole.SUPERADMIN.value:
        query = query.join(models.Brand, models.Brand.id == models.GenerationJob.brand_id).filter(
            models.Brand.tenant_id == current_user.tenant_id
        )
    if status_filter is not None:
        query = query.filter(models.PresentationReview.moderation_status == status_filter)

    reviews = query.order_by(models.PresentationReview.created_at.desc()).all()
    return [
        {
            **_serialize_review(r),
            "job_display_name": portfolio_display_name(r.job) if r.job else None,
        }
        for r in reviews
    ]


@router.patch("/api/admin/reviews/{review_id}/moderation")
def update_review_moderation(review_id: int, request: ModerationUpdateRequest, db: Session = Depends(get_db), current_user: models.User = Depends(require_role(models.UserRole.ADMIN.value, models.UserRole.SUPERADMIN.value))):
    """Admin del tenant del job (o superadmin) puede pasar una review a visible/hidden. Nunca a 'flagged' manualmente."""
    if request.status not in ("visible", "hidden"):
        raise HTTPException(status_code=422, detail="status must be 'visible' or 'hidden'")

    review = db.query(models.PresentationReview).get(review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    job = db.query(models.GenerationJob).get(review.job_id)
    check_job_tenant_access(db, current_user, job)

    review.moderation_status = request.status
    db.commit()
    return _serialize_review(review)


@router.get("/api/admin/config/review-moderation-blocklist")
def get_moderation_blocklist(db: Session = Depends(get_db), current_user: models.User = Depends(require_role(models.UserRole.SUPERADMIN.value))):
    """Lee la blocklist actual (para poblar el editor del panel admin)."""
    return {"terms": content_moderation_service.get_blocklist(db)}


@router.patch("/api/admin/config/review-moderation-blocklist")
def update_moderation_blocklist(request: BlocklistUpdateRequest, db: Session = Depends(get_db), current_user: models.User = Depends(require_role(models.UserRole.SUPERADMIN.value))):
    """Reemplaza la blocklist de moderación de reviews. Superadmin only (config global, no por tenant)."""
    cfg = db.query(models.SystemConfig).filter(
        models.SystemConfig.key == content_moderation_service.BLOCKLIST_CONFIG_KEY
    ).first()
    value = json.dumps(request.terms)
    if cfg is None:
        cfg = models.SystemConfig(key=content_moderation_service.BLOCKLIST_CONFIG_KEY, value=value)
        db.add(cfg)
    else:
        cfg.value = value
    db.commit()
    return {"terms": request.terms}
