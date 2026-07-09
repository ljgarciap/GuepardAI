"""
routers/analytics.py — Analítica de uso por usuario/departamento
(reviews-analitica-colaboracion, ítem 5).

Spec: docs/specs/reviews-analitica-colaboracion.md
Design: docs/designs/reviews-analitica-colaboracion.md §5
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

import models
from auth.dependencies import check_job_tenant_access, get_current_user, require_role
from database import get_db

router = APIRouter(tags=["Analytics"])

_ADMIN_ROLES = (models.UserRole.ADMIN.value, models.UserRole.SUPERADMIN.value)


class ActivityEventRequest(BaseModel):
    event_type: str
    value: int


@router.post("/api/presentations/{job_id}/activity")
def record_activity_event(job_id: int, request: ActivityEventRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Evento de frontend (navigator.sendBeacon al salir del generador). Solo session_time_seconds
    — slide_edit se registra server-side en PUT /slides/{slide_id}, no es postable por el cliente."""
    if request.event_type != "session_time_seconds":
        raise HTTPException(status_code=422, detail="event_type must be 'session_time_seconds'")
    if request.value <= 0:
        raise HTTPException(status_code=422, detail="value must be a positive number of seconds")

    job = db.query(models.GenerationJob).get(job_id)
    check_job_tenant_access(db, current_user, job)

    db.add(models.UserActivityEvent(job_id=job_id, user_id=current_user.id, event_type="session_time_seconds", value=request.value))
    db.commit()
    return {"status": "recorded"}


@router.get("/api/admin/analytics/usage")
def get_usage_analytics(
    tenant_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(*_ADMIN_ROLES)),
):
    """Agregado por usuario: presentaciones creadas, ediciones, tiempo invertido, rating
    promedio recibido. Admin ve solo su tenant; superadmin ve todo (o filtra por tenant_id).

    Agregados en 4 queries GROUP BY (mas la lista de usuarios) en vez de un loop con 4-5
    queries por usuario — antes era ~5N queries no acotadas, sin paginación de usuarios."""
    query = db.query(models.User).options(joinedload(models.User.department))
    if current_user.role == models.UserRole.SUPERADMIN.value:
        if tenant_id is not None:
            query = query.filter(models.User.tenant_id == tenant_id)
        else:
            query = query.filter(models.User.tenant_id.isnot(None))
    else:
        query = query.filter(models.User.tenant_id == current_user.tenant_id)
    users = query.all()
    user_ids = [u.id for u in users]

    if not user_ids:
        return {"users": []}

    presentations_by_user = dict(
        db.query(models.GenerationJob.owner_id, func.count(models.GenerationJob.id))
        .filter(models.GenerationJob.owner_id.in_(user_ids))
        .group_by(models.GenerationJob.owner_id)
        .all()
    )
    edits_by_user = dict(
        db.query(models.UserActivityEvent.user_id, func.coalesce(func.sum(models.UserActivityEvent.value), 0))
        .filter(models.UserActivityEvent.user_id.in_(user_ids), models.UserActivityEvent.event_type == "slide_edit")
        .group_by(models.UserActivityEvent.user_id)
        .all()
    )
    time_by_user = dict(
        db.query(models.UserActivityEvent.user_id, func.coalesce(func.sum(models.UserActivityEvent.value), 0))
        .filter(models.UserActivityEvent.user_id.in_(user_ids), models.UserActivityEvent.event_type == "session_time_seconds")
        .group_by(models.UserActivityEvent.user_id)
        .all()
    )
    rating_by_user = dict(
        db.query(models.GenerationJob.owner_id, func.avg(models.PresentationReview.rating))
        .join(models.PresentationReview, models.PresentationReview.job_id == models.GenerationJob.id)
        .filter(
            models.GenerationJob.owner_id.in_(user_ids),
            models.PresentationReview.is_deleted == False,
            models.PresentationReview.moderation_status != "hidden",
        )
        .group_by(models.GenerationJob.owner_id)
        .all()
    )

    results = []
    for user in users:
        rating = rating_by_user.get(user.id)
        results.append({
            "user_id": user.id,
            "email": user.email,
            "department_id": user.department_id,
            "department_name": user.department.name if user.department else None,
            "presentations_created": presentations_by_user.get(user.id, 0),
            "edits": int(edits_by_user.get(user.id, 0)),
            "time_spent_seconds": int(time_by_user.get(user.id, 0)),
            "rating_average_received": round(rating, 2) if rating is not None else None,
        })

    return {"users": results}


@router.get("/api/admin/usage-reports")
def list_usage_reports(
    tenant_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(*_ADMIN_ROLES)),
):
    """Reportes mensuales persistidos (ítem 7) — fuente de verdad visual si el envío por
    email falla o Celery beat no está desplegado. Admin ve solo los de su tenant;
    superadmin ve todos (incluido el global, tenant_id NULL) salvo que filtre por tenant_id."""
    query = db.query(models.UsageReport)
    if current_user.role == models.UserRole.SUPERADMIN.value:
        if tenant_id is not None:
            query = query.filter(models.UsageReport.tenant_id == tenant_id)
    else:
        query = query.filter(models.UsageReport.tenant_id == current_user.tenant_id)

    reports = query.order_by(models.UsageReport.period_start.desc()).all()
    return [
        {
            "id": r.id,
            "tenant_id": r.tenant_id,
            "period_start": r.period_start,
            "period_end": r.period_end,
            "payload": r.payload_json,
            "created_at": r.created_at,
            "sent_at": r.sent_at,
        }
        for r in reports
    ]
