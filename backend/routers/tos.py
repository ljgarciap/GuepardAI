"""
routers/tos.py — Aceptación de Términos de Servicio por usuario. Solo glue:
la lógica vive en services/core/auth_service.py (convención del proyecto).

Deliberadamente bajo /api/tos, exento del gate de ToS en auth/dependencies.py
(TOS_EXEMPT_PATH_PREFIXES) — un usuario bloqueado debe poder llegar a estas
rutas para aceptar y recuperar acceso.

Spec: docs/designs/claude-skills-benchmark-and-team-feedback-2026-07.md §5
"""
import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from database import get_db
from auth.dependencies import get_current_user
from services.core import auth_service

router = APIRouter(prefix="/api/tos", tags=["ToS"])


class TosStatusOut(BaseModel):
    accepted: bool
    current_version: str
    accepted_version: Optional[str] = None
    accepted_at: Optional[datetime.datetime] = None
    rejected_at: Optional[datetime.datetime] = None


@router.get("/status", response_model=TosStatusOut)
def get_status(user: models.User = Depends(get_current_user)):
    return auth_service.get_tos_status(user)


@router.post("/accept", response_model=TosStatusOut)
def accept(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return auth_service.accept_tos(db, user)


@router.post("/reject", response_model=TosStatusOut)
def reject(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return auth_service.reject_tos(db, user)
