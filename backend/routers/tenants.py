"""
routers/tenants.py — Alta y listado de Tenants por el superadmin.

El único camino previo para crear un Tenant era el autoregistro público
(POST /api/auth/register). Este router agrega el camino administrado: el
superadmin crea un Tenant nuevo junto con su primer Admin, sin pasar por el
flujo público. También expone el listado que alimenta los selectores de
tenant en el Admin Panel (Departments, Analytics, Reports) — antes esos
selectores eran inputs numéricos crudos con el tenant_id.

Spec: docs/specs/gestion-tenants-superadmin.md
Design: docs/designs/gestion-tenants-superadmin.md
"""
import datetime
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

import models
from auth.dependencies import require_role
from database import get_db
from services.core import auth_service

router = APIRouter(prefix="/api/admin/tenants", tags=["Tenants"])

_SUPERADMIN_ONLY = (models.UserRole.SUPERADMIN.value,)


class TenantOut(BaseModel):
    id: int
    name: str
    is_active: int
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class TenantCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    admin_email: EmailStr
    admin_password: str = Field(..., min_length=8)


class TenantAdminOut(BaseModel):
    id: int
    email: str

    class Config:
        from_attributes = True


class TenantCreateResponse(BaseModel):
    tenant: TenantOut
    admin: TenantAdminOut


@router.get("", response_model=List[TenantOut])
def list_tenants(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(*_SUPERADMIN_ONLY)),
):
    return db.query(models.Tenant).order_by(models.Tenant.name).all()


@router.post("", response_model=TenantCreateResponse, status_code=201)
def create_tenant(
    payload: TenantCreateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(*_SUPERADMIN_ONLY)),
):
    tenant, admin = auth_service.create_tenant_with_admin(
        db, tenant_name=payload.name, admin_email=payload.admin_email, admin_password=payload.admin_password
    )
    return {"tenant": tenant, "admin": admin}
