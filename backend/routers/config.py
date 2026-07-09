"""
routers/config.py — Config expuesta al frontend, sin scoping de tenant
(taxonomías globales fijas/seedeadas).

Spec: docs/specs/soporte-indicaciones.md
Design: docs/designs/soporte-indicaciones.md
"""
import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import models
from auth.dependencies import get_current_user
from database import get_db

router = APIRouter(prefix="/api/config", tags=["Config"])


@router.get("/prompt-intents")
def get_prompt_intents(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Biblioteca de intenciones (compositor guiado) tal cual está en system_configs — global, cualquier rol."""
    cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == "intent_library_v1").first()
    if cfg is None or not cfg.value:
        return []
    try:
        return json.loads(cfg.value)
    except (TypeError, ValueError):
        return []
