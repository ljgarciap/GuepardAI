"""
routers/departments.py — Catálogo de departamentos administrado por tenant.

Spec: docs/specs/reviews-analitica-colaboracion.md
Design: docs/designs/reviews-analitica-colaboracion.md §4
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
from auth.dependencies import require_role
from database import get_db

router = APIRouter(prefix="/api/admin/departments", tags=["Departments"])

_ADMIN_ROLES = (models.UserRole.ADMIN.value, models.UserRole.SUPERADMIN.value)


class DepartmentCreateRequest(BaseModel):
    name: str
    tenant_id: Optional[int] = None  # solo lo honra un superadmin; admin siempre usa su propio tenant


class DepartmentOut(BaseModel):
    id: int
    tenant_id: int
    name: str

    class Config:
        from_attributes = True


@router.post("", response_model=DepartmentOut, status_code=201)
def create_department(
    payload: DepartmentCreateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(*_ADMIN_ROLES)),
):
    if current_user.role == models.UserRole.SUPERADMIN.value:
        if payload.tenant_id is None:
            raise HTTPException(status_code=422, detail="tenant_id is required for superadmin")
        target_tenant_id = payload.tenant_id
    else:
        target_tenant_id = current_user.tenant_id

    department = models.Department(tenant_id=target_tenant_id, name=payload.name)
    db.add(department)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Department name already exists for this tenant")
    db.refresh(department)
    return department


@router.get("", response_model=List[DepartmentOut])
def list_departments(
    tenant_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(*_ADMIN_ROLES)),
):
    query = db.query(models.Department)
    if current_user.role == models.UserRole.SUPERADMIN.value:
        if tenant_id is not None:
            query = query.filter(models.Department.tenant_id == tenant_id)
    else:
        query = query.filter(models.Department.tenant_id == current_user.tenant_id)
    return query.order_by(models.Department.name).all()


@router.delete("/{department_id}")
def delete_department(
    department_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(*_ADMIN_ROLES)),
):
    department = db.query(models.Department).filter(models.Department.id == department_id).first()
    if department is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
    if current_user.role != models.UserRole.SUPERADMIN.value and department.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Department belongs to a different tenant")

    has_users = db.query(models.User).filter(models.User.department_id == department_id).first() is not None
    if has_users:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Department has users assigned — reassign or clear them first")

    db.delete(department)
    db.commit()
    return {"status": "deleted"}
