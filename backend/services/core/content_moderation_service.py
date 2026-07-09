"""
content_moderation_service.py — Filtro de palabras/frases para reviews (v1).

Determinista, sin LLM: coincidencia de substring case-insensitive contra una
blocklist en `system_configs` (key `review_moderation_blocklist_v1`, lista
JSON de términos). No es un BaseAgentTool porque no es una decisión de IA.

Spec: docs/specs/reviews-analitica-colaboracion.md
Design: docs/designs/reviews-analitica-colaboracion.md §3
"""
import json
from typing import Literal

from sqlalchemy.orm import Session

import models

BLOCKLIST_CONFIG_KEY = "review_moderation_blocklist_v1"


def get_blocklist(db: Session) -> list[str]:
    """Términos tal cual fueron guardados (para mostrar/editar en el panel admin)."""
    cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == BLOCKLIST_CONFIG_KEY).first()
    if cfg is None or not cfg.value:
        return []
    try:
        terms = json.loads(cfg.value)
    except (TypeError, ValueError):
        return []
    if not isinstance(terms, list):
        return []
    return [str(t) for t in terms if str(t).strip()]


def evaluate(db: Session, text: str) -> Literal["visible", "flagged"]:
    """Marca `flagged` si `text` contiene algún término de la blocklist (substring, case-insensitive)."""
    if not text:
        return "visible"
    lowered = text.lower()
    for term in get_blocklist(db):
        if term.lower() in lowered:
            return "flagged"
    return "visible"
