"""
routers/auth.py — Endpoints de autenticación. Solo glue: la lógica de negocio
vive en services/core/auth_service.py (convención del proyecto).

Spec: docs/specs/autenticacion-multiusuario-multitenant.md
Design: docs/designs/autenticacion-multitenant-design.md §3.2
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

import models
from database import get_db
from auth.dependencies import check_login_rate_limit, get_current_user
from auth.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from services.core import auth_service

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    _user, access_token, refresh_token = auth_service.register_user(
        db, email=payload.email, password=payload.password, tenant_name=payload.tenant_name
    )
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    check_login_rate_limit(request, payload.email)
    _user, access_token, refresh_token = auth_service.authenticate_user(
        db, payload.email, payload.password
    )
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    access_token, refresh_token = auth_service.refresh_access_token(db, payload.refresh_token)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout", status_code=204)
def logout_route(payload: LogoutRequest):
    auth_service.logout(payload.refresh_token)


@router.get("/me", response_model=UserOut)
def me(user: models.User = Depends(get_current_user)):
    return user
