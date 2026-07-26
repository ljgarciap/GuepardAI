"""
schemas.py — Pydantic request/response models del módulo de auth.

Spec: docs/specs/autenticacion-multiusuario-multitenant.md
"""
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    tenant_name: Optional[str] = None  # nombre visible del tenant; default = email


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: str
    tenant_id: Optional[int] = None
    is_active: int
    department_id: Optional[int] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


class CreateUserRequest(BaseModel):
    """
    Alta de un usuario `cliente`. `tenant_id` solo lo honra un `superadmin`
    (un `admin` siempre crea en su propio tenant, ignora este campo).
    """
    email: EmailStr
    password: str = Field(..., min_length=8)
    tenant_id: Optional[int] = None
