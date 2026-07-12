"""
routers/prompt_favorites.py — CRUD de prompts favoritos (Ayuda 4 de
soporte-indicaciones, spec propia).

Visibilidad de lectura en 3 niveles (cliente ve los propios, admin ve los de
su tenant, superadmin ve todos) — escritura (PUT/DELETE) exclusiva del dueño
en todos los roles, sin excepción. Ver docs/designs/biblioteca-prompts-favoritos.md
§"Riesgo arquitectónico principal" antes de tocar la autorización acá.

Spec: docs/specs/biblioteca-prompts-favoritos.md
Design: docs/designs/biblioteca-prompts-favoritos.md
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
from auth.dependencies import get_current_user
from database import get_db

router = APIRouter(prefix="/api/prompts/favorites", tags=["Prompt Favorites"])


class PromptFavoriteCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    prompt_text: str = Field(..., min_length=1)
    prompt_metadata: Optional[dict] = None
    source_job_id: Optional[int] = None


class PromptFavoriteUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=120)
    prompt_text: Optional[str] = Field(None, min_length=1)
    prompt_metadata: Optional[dict] = None


def _visible_favorites_query(db: Session, current_user: models.User):
    """
    Visibilidad de lectura de 3 niveles, exclusiva de PromptFavorite — NO usar
    como puerta de escritura (ver _get_favorite_or_404 + chequeo de owner_id
    explícito en update/delete más abajo).
    """
    query = db.query(models.PromptFavorite)
    if current_user.role == models.UserRole.SUPERADMIN.value:
        return query
    if current_user.role == models.UserRole.ADMIN.value:
        return query.filter(models.PromptFavorite.tenant_id == current_user.tenant_id)
    return query.filter(models.PromptFavorite.user_id == current_user.id)


def _get_favorite_or_404(db: Session, current_user: models.User, favorite_id: int) -> models.PromptFavorite:
    fav = _visible_favorites_query(db, current_user).filter(
        models.PromptFavorite.id == favorite_id
    ).first()
    if fav is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Favorite not found")
    return fav


def _serialize(db: Session, fav: models.PromptFavorite) -> dict:
    owner = db.query(models.User).filter(models.User.id == fav.user_id).first()
    return {
        "id": fav.id,
        "title": fav.title,
        "prompt_text": fav.prompt_text,
        "prompt_metadata": fav.prompt_metadata,
        "source_job_id": fav.source_job_id,
        "owner_email": owner.email if owner else None,
        "created_at": fav.created_at,
        "updated_at": fav.updated_at,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_favorite(
    payload: PromptFavoriteCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    fav = models.PromptFavorite(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        title=payload.title,
        prompt_text=payload.prompt_text,
        prompt_metadata=payload.prompt_metadata,
        source_job_id=payload.source_job_id,
    )
    db.add(fav)
    db.commit()
    db.refresh(fav)
    return _serialize(db, fav)


@router.get("")
def list_favorites(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    favorites = _visible_favorites_query(db, current_user).order_by(
        models.PromptFavorite.created_at.desc()
    ).all()
    return [_serialize(db, fav) for fav in favorites]


@router.put("/{favorite_id}")
def update_favorite(
    favorite_id: int,
    payload: PromptFavoriteUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    fav = _get_favorite_or_404(db, current_user, favorite_id)
    if fav.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner can edit this favorite")

    if payload.title is not None:
        fav.title = payload.title
    if payload.prompt_text is not None:
        fav.prompt_text = payload.prompt_text
    if payload.prompt_metadata is not None:
        fav.prompt_metadata = payload.prompt_metadata
    db.commit()
    db.refresh(fav)
    return _serialize(db, fav)


@router.delete("/{favorite_id}")
def delete_favorite(
    favorite_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    fav = _get_favorite_or_404(db, current_user, favorite_id)
    if fav.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner can delete this favorite")

    db.delete(fav)
    db.commit()
    return {"deleted": True, "id": favorite_id}
