"""
routers/users.py — Gestión de usuarios `cliente` por un admin (o por un
superadmin, sin restricción de tenant).

Spec: docs/specs/autenticacion-multiusuario-multitenant.md
Design: docs/designs/autenticacion-multitenant-design.md §3.2
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
from auth import security
from auth.dependencies import require_role
from auth.schemas import CreateUserRequest, UserOut
from database import get_db

router = APIRouter(prefix="/api/users", tags=["Users"])

_ADMIN_ROLES = (models.UserRole.ADMIN.value, models.UserRole.SUPERADMIN.value)


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    payload: CreateUserRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(*_ADMIN_ROLES)),
):
    if current_user.role == models.UserRole.SUPERADMIN.value:
        target_tenant_id = payload.tenant_id if payload.tenant_id is not None else current_user.tenant_id
    else:
        target_tenant_id = current_user.tenant_id  # admin: siempre su propio tenant, payload.tenant_id se ignora

    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    new_user = models.User(
        email=payload.email,
        hashed_password=security.hash_password(payload.password),
        role=models.UserRole.CLIENTE.value,
        tenant_id=target_tenant_id,
        is_active=1,
    )
    db.add(new_user)
    try:
        db.commit()
    except IntegrityError:
        # Misma carrera que en auth_service.register_user: dos altas
        # concurrentes con el mismo email pasan el SELECT antes de que
        # cualquiera comitee. Sin este catch, 500 crudo en vez de 409.
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")
    db.refresh(new_user)
    return new_user


@router.get("", response_model=List[UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(*_ADMIN_ROLES)),
):
    query = db.query(models.User)
    if current_user.role != models.UserRole.SUPERADMIN.value:
        query = query.filter(models.User.tenant_id == current_user.tenant_id)
    return query.order_by(models.User.id).all()


@router.patch("/{user_id}/deactivate", response_model=UserOut)
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(*_ADMIN_ROLES)),
):
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if current_user.role != models.UserRole.SUPERADMIN.value and target.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User belongs to a different tenant")

    target.is_active = 0
    db.commit()
    db.refresh(target)
    return target
