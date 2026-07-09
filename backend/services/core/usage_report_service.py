"""
usage_report_service.py — Agregación y envío de reportes mensuales de uso
(reviews-analitica-colaboracion, ítem 7).

Disparado por Celery beat (ver celery_app.py beat_schedule) el día 1 de cada
mes vía tasks.generate_monthly_usage_report. Genera un UsageReport por tenant
más uno global (tenant_id NULL, solo superadmin), y envía cada uno por email
al/los admin(es) correspondientes vía email_service (tolerante: si SMTP no
está configurado, el reporte queda igual persistido y visible en
GET /api/admin/usage-reports — el envío es best-effort, nunca bloqueante).

Spec: docs/specs/reviews-analitica-colaboracion.md
Design: docs/designs/reviews-analitica-colaboracion.md §6
"""
import calendar
import datetime
import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from database import SessionLocal
from services.core import email_service

logger = logging.getLogger(__name__)


def _previous_month_period(now: datetime.datetime) -> tuple[datetime.datetime, datetime.datetime]:
    """(period_start, period_end) del mes calendario anterior a `now`, ambos inclusive-exclusive
    en el sentido [start, end) para usar en comparaciones created_at >= start AND created_at < end."""
    first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    period_end = first_of_this_month
    prev_month_index = (first_of_this_month.month - 2) % 12 + 1
    prev_year = first_of_this_month.year - 1 if first_of_this_month.month == 1 else first_of_this_month.year
    period_start = first_of_this_month.replace(year=prev_year, month=prev_month_index)
    return period_start, period_end


def _aggregate_scope(db: Session, user_ids: list[int], period_start: datetime.datetime, period_end: datetime.datetime) -> dict:
    """Agregado de actividad para un conjunto de user_ids en [period_start, period_end)."""
    if not user_ids:
        return {
            "presentations_created": 0, "total_edits": 0, "total_time_spent_seconds": 0,
            "rating_average": None, "contributors_count": 0, "top_user": None, "top_department": None,
        }

    presentations_created = db.query(func.count(models.GenerationJob.id)).filter(
        models.GenerationJob.owner_id.in_(user_ids),
        models.GenerationJob.created_at >= period_start,
        models.GenerationJob.created_at < period_end,
    ).scalar() or 0

    activity_period_filter = (
        models.UserActivityEvent.user_id.in_(user_ids),
        models.UserActivityEvent.created_at >= period_start,
        models.UserActivityEvent.created_at < period_end,
    )
    total_edits = db.query(func.coalesce(func.sum(models.UserActivityEvent.value), 0)).filter(
        *activity_period_filter, models.UserActivityEvent.event_type == "slide_edit",
    ).scalar() or 0
    total_time_spent_seconds = db.query(func.coalesce(func.sum(models.UserActivityEvent.value), 0)).filter(
        *activity_period_filter, models.UserActivityEvent.event_type == "session_time_seconds",
    ).scalar() or 0

    rating_average = db.query(func.avg(models.PresentationReview.rating)).join(
        models.GenerationJob, models.GenerationJob.id == models.PresentationReview.job_id
    ).filter(
        models.GenerationJob.owner_id.in_(user_ids),
        models.PresentationReview.is_deleted == False,
        models.PresentationReview.moderation_status != "hidden",
        models.PresentationReview.created_at >= period_start,
        models.PresentationReview.created_at < period_end,
    ).scalar()

    contributors_count = db.query(func.count(func.distinct(models.UserActivityEvent.user_id))).filter(
        *activity_period_filter
    ).scalar() or 0

    top_user_row = db.query(
        models.UserActivityEvent.user_id,
        func.sum(models.UserActivityEvent.value).label("total")
    ).filter(*activity_period_filter).group_by(models.UserActivityEvent.user_id).order_by(func.sum(models.UserActivityEvent.value).desc()).first()
    top_user = None
    if top_user_row is not None:
        top_user_obj = db.query(models.User).get(top_user_row.user_id)
        top_user = {"user_id": top_user_row.user_id, "email": top_user_obj.email if top_user_obj else None, "activity_total": int(top_user_row.total)}

    top_department_row = db.query(
        models.User.department_id,
        func.sum(models.UserActivityEvent.value).label("total")
    ).join(models.User, models.User.id == models.UserActivityEvent.user_id).filter(
        *activity_period_filter, models.User.department_id.isnot(None)
    ).group_by(models.User.department_id).order_by(func.sum(models.UserActivityEvent.value).desc()).first()
    top_department = None
    if top_department_row is not None:
        dept = db.query(models.Department).get(top_department_row.department_id)
        top_department = {"department_id": top_department_row.department_id, "name": dept.name if dept else None, "activity_total": int(top_department_row.total)}

    return {
        "presentations_created": presentations_created,
        "total_edits": int(total_edits),
        "total_time_spent_seconds": int(total_time_spent_seconds),
        "rating_average": round(rating_average, 2) if rating_average is not None else None,
        "contributors_count": contributors_count,
        "top_user": top_user,
        "top_department": top_department,
    }


def _report_recipients(db: Session, tenant_id: int | None) -> list[str]:
    if tenant_id is None:
        users = db.query(models.User).filter(models.User.role == models.UserRole.SUPERADMIN.value).all()
    else:
        users = db.query(models.User).filter(
            models.User.tenant_id == tenant_id, models.User.role == models.UserRole.ADMIN.value
        ).all()
    return [u.email for u in users]


def generate_and_send_monthly_reports() -> dict:
    """Entry point llamado por tasks.generate_monthly_usage_report. Genera + persiste + envía
    un UsageReport por tenant y uno global. Devuelve un resumen serializable."""
    db = SessionLocal()
    summary = {"reports_created": 0, "emails_sent": 0, "emails_skipped": 0}
    try:
        period_start, period_end = _previous_month_period(datetime.datetime.utcnow())

        tenants = db.query(models.Tenant).all()
        scopes: list[tuple[int | None, list[int]]] = []
        for tenant in tenants:
            user_ids = [u.id for u in db.query(models.User.id).filter(models.User.tenant_id == tenant.id).all()]
            scopes.append((tenant.id, user_ids))
        # Global: todos los usuarios con tenant asignado (superadmin no tiene owner_id propio relevante).
        all_user_ids = [u.id for u in db.query(models.User.id).filter(models.User.tenant_id.isnot(None)).all()]
        scopes.append((None, all_user_ids))

        for tenant_id, user_ids in scopes:
            payload = _aggregate_scope(db, user_ids, period_start, period_end)
            report = models.UsageReport(
                tenant_id=tenant_id, period_start=period_start, period_end=period_end, payload_json=payload,
            )
            db.add(report)
            db.commit()
            db.refresh(report)
            summary["reports_created"] += 1

            recipients = _report_recipients(db, tenant_id)
            subject = f"GuepardAI — Reporte de uso {period_start.strftime('%B %Y')}"
            body = (
                f"Presentaciones creadas: {payload['presentations_created']}\n"
                f"Ediciones totales: {payload['total_edits']}\n"
                f"Tiempo invertido (seg): {payload['total_time_spent_seconds']}\n"
                f"Rating promedio: {payload['rating_average']}\n"
                f"Contribuidores activos: {payload['contributors_count']}\n"
            )
            any_sent = False
            for recipient in recipients:
                if email_service.send_email(recipient, subject, body):
                    any_sent = True
                    summary["emails_sent"] += 1
                else:
                    summary["emails_skipped"] += 1
            if any_sent:
                report.sent_at = datetime.datetime.utcnow()
                db.commit()

        return summary
    except Exception as e:
        logger.error(f"[UsageReportService] Monthly report generation failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()
