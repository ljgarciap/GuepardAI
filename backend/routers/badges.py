"""
routers/badges.py — Gamificación (reviews-analitica-colaboracion, ítem 8).
Sin tabla nueva: cálculo on-demand sobre GenerationJob.owner_id. Umbrales
configurables vía system_configs (badge_thresholds_v1), no hardcodeados.

Spec: docs/specs/reviews-analitica-colaboracion.md
Design: docs/designs/reviews-analitica-colaboracion.md §7
"""
import json

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from auth.dependencies import get_current_user
from database import get_db

router = APIRouter(prefix="/api/users/me", tags=["Badges"])

BADGE_THRESHOLDS_CONFIG_KEY = "badge_thresholds_v1"
_DEFAULT_THRESHOLDS = [{"threshold": 5, "label": "Starter"}, {"threshold": 10, "label": "Expert"}, {"threshold": 20, "label": "Genius"}]


def _get_thresholds(db: Session) -> list[dict]:
    cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == BADGE_THRESHOLDS_CONFIG_KEY).first()
    if cfg is None or not cfg.value:
        return _DEFAULT_THRESHOLDS
    try:
        thresholds = json.loads(cfg.value)
    except (TypeError, ValueError):
        return _DEFAULT_THRESHOLDS
    if not isinstance(thresholds, list) or not thresholds:
        return _DEFAULT_THRESHOLDS
    return sorted(thresholds, key=lambda t: t["threshold"])


@router.get("/badges")
def get_my_badges(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """count, current_badge (última insignia alcanzada o None), next_badge, progress_to_next."""
    count = db.query(func.count(models.GenerationJob.id)).filter(
        models.GenerationJob.owner_id == current_user.id
    ).scalar() or 0

    thresholds = _get_thresholds(db)
    current_badge = None
    next_badge = None
    for t in thresholds:
        if count >= t["threshold"]:
            current_badge = t
        elif next_badge is None:
            next_badge = t

    progress_to_next = None
    if next_badge is not None:
        floor = current_badge["threshold"] if current_badge else 0
        span = next_badge["threshold"] - floor
        progress_to_next = round((count - floor) / span, 2) if span > 0 else 1.0

    return {
        "count": count,
        "current_badge": current_badge,
        "next_badge": next_badge,
        "progress_to_next": progress_to_next,
    }
