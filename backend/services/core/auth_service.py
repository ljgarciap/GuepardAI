"""
auth_service.py — Lógica de negocio de autenticación (registro, login, refresh, logout).

Routers solo hacen de glue (routers/auth.py); toda la lógica vive acá, según
la convención del proyecto.

Spec: docs/specs/autenticacion-multiusuario-multitenant.md
Design: docs/designs/autenticacion-multitenant-design.md §2.4, §3.2, §3.6
"""
import datetime
from typing import Optional, Tuple

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
from auth import security
from auth.redis_client import get_redis_client

REFRESH_KEY_PREFIX = "refresh"

# Hash fijo usado SOLO para igualar el costo de CPU cuando el email no existe
# o la cuenta está inactiva — sin esto, authenticate_user retorna casi
# instantáneo en esas ramas pero corre un hash bcrypt (deliberadamente lento)
# cuando el email sí existe, dejando un side-channel de timing que revela
# si una cuenta existe/está activa (Senior Reviewer, blocker #1, 2026-07-05).
_DUMMY_PASSWORD_HASH = security.hash_password("dummy-password-for-constant-time-comparison")


def _refresh_key(jti: str) -> str:
    return f"{REFRESH_KEY_PREFIX}:{jti}"


def _issue_token_pair(user: models.User) -> Tuple[str, str]:
    access_token = security.create_access_token(user.id, user.role, user.tenant_id)
    refresh_token, jti, expires_at = security.create_refresh_token(user.id)
    ttl_seconds = max(int((expires_at - datetime.datetime.utcnow()).total_seconds()), 1)
    get_redis_client().set(_refresh_key(jti), str(user.id), ex=ttl_seconds)
    return access_token, refresh_token


def _create_tenant_and_admin(db: Session, email: str, password: str, tenant_name: str) -> Tuple[models.Tenant, models.User]:
    """Crea un Tenant nuevo y su primer User rol `admin` (nunca `cliente` suelto —
    un tenant recién creado necesita alguien que lo administre). Compartido por
    register_user (autoregistro público) y create_tenant_with_admin (alta por
    superadmin desde el Admin Panel)."""
    existing = db.query(models.User).filter(models.User.email == email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    tenant = models.Tenant(name=tenant_name)
    db.add(tenant)
    db.flush()  # asigna tenant.id sin cerrar la transacción

    user = models.User(
        email=email,
        hashed_password=security.hash_password(password),
        role=models.UserRole.ADMIN.value,
        tenant_id=tenant.id,
        is_active=1,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Carrera: dos altas concurrentes con el mismo email pasaron el SELECT
        # de arriba antes de que cualquiera hiciera commit. El unique constraint
        # de la DB es la última línea de defensa — sin este catch, el segundo
        # request recibe un 500 crudo en vez del 409 documentado.
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")
    db.refresh(tenant)
    db.refresh(user)
    return tenant, user


def register_user(
    db: Session, email: str, password: str, tenant_name: Optional[str] = None
) -> Tuple[models.User, str, str]:
    """Registro público: crea Tenant + primer Admin y devuelve un par de tokens
    para dejar al usuario logueado. Resolución confirmada por Luis 2026-07-05, ver spec."""
    _tenant, user = _create_tenant_and_admin(db, email, password, tenant_name or email)
    access_token, refresh_token = _issue_token_pair(user)
    return user, access_token, refresh_token


def create_tenant_with_admin(
    db: Session, tenant_name: str, admin_email: str, admin_password: str
) -> Tuple[models.Tenant, models.User]:
    """Alta de Tenant + Admin por un superadmin desde el Admin Panel (no autoregistro).
    No emite tokens — el superadmin mantiene su propia sesión; el admin nuevo
    inicia sesión con la password que el superadmin le comunique fuera de banda.
    Decisión temporal confirmada por Luis 2026-07-12: migrar a invitación por
    email con password temporal más adelante (ver spec, sección "Futuro")."""
    return _create_tenant_and_admin(db, admin_email, admin_password, tenant_name)


def authenticate_user(db: Session, email: str, password: str) -> Tuple[models.User, str, str]:
    """
    Mismo mensaje de error para email inexistente, cuenta inactiva y password
    incorrecta — evita enumeración por contenido. `verify_password` corre
    SIEMPRE (contra el hash real si el usuario existe, contra un hash dummy
    si no) para que el tiempo de respuesta tampoco delate cuál caso ocurrió.
    """
    generic_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password"
    )

    user = db.query(models.User).filter(models.User.email == email).first()
    hash_to_check = user.hashed_password if user is not None else _DUMMY_PASSWORD_HASH
    password_valid = security.verify_password(password, hash_to_check)

    if user is None or not user.is_active or not password_valid:
        raise generic_error

    access_token, refresh_token = _issue_token_pair(user)
    return user, access_token, refresh_token


def change_password(db: Session, user: models.User, current_password: str, new_password: str) -> None:
    """Requiere la password actual (no alcanza con el access token) — evita que
    una sesión abierta/robada cambie la password sin que el dueño la sepa."""
    if not security.verify_password(current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

    user.hashed_password = security.hash_password(new_password)
    db.commit()


def refresh_access_token(db: Session, refresh_token: str) -> Tuple[str, str]:
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token"
    )
    try:
        payload = security.decode_token(refresh_token)
    except JWTError:
        raise invalid
    if payload.get("type") != "refresh":
        raise invalid

    jti = payload.get("jti")
    user_id = payload.get("sub")
    r = get_redis_client()
    try:
        # GETDEL es atómico: lee y borra en una sola operación, así que dos
        # requests de refresh concurrentes con el mismo token no pueden
        # ambos leer el valor antes de que cualquiera lo borre (TOCTOU que
        # existía con r.get() + r.delete() separados — Senior Reviewer #3).
        stored_user_id = r.getdel(_refresh_key(jti))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Session store unavailable"
        )
    if stored_user_id is None or stored_user_id != str(user_id):
        raise invalid

    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if user is None or not user.is_active:
        raise invalid

    return _issue_token_pair(user)


def logout(refresh_token: str) -> None:
    try:
        payload = security.decode_token(refresh_token)
    except JWTError:
        return  # token ya inválido: logout es idempotente, no hay nada que revocar
    jti = payload.get("jti")
    if not jti:
        return
    try:
        get_redis_client().delete(_refresh_key(jti))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Session store unavailable"
        )


# ---------------------------------------------------------------------------
# Términos de Servicio — aceptación por usuario.
# Spec: docs/designs/claude-skills-benchmark-and-team-feedback-2026-07.md §5.
# El gate real vive en auth/dependencies.py (get_current_user); estas
# funciones son la única fuente de verdad que ese gate y routers/tos.py
# comparten, para que nunca queden desincronizados.
# ---------------------------------------------------------------------------

TOS_CURRENT_VERSION_CONFIG_KEY = "tos_current_version"
TOS_DEFAULT_VERSION = "1.1"


def get_current_tos_version() -> str:
    from providers.llm_provider import get_system_config
    return get_system_config(TOS_CURRENT_VERSION_CONFIG_KEY, TOS_DEFAULT_VERSION)


def has_accepted_current_tos(user: models.User) -> bool:
    """superadmin es la cuenta operativa de la plataforma, no un `Client` sujeto
    al ToS — bypass explícito por rol, igual que el resto del scoping por tenant."""
    if user.role == models.UserRole.SUPERADMIN.value:
        return True
    return user.tos_accepted == 1 and user.tos_accepted_version == get_current_tos_version()


def get_tos_status(user: models.User) -> dict:
    return {
        "accepted": has_accepted_current_tos(user),
        "current_version": get_current_tos_version(),
        "accepted_version": user.tos_accepted_version,
        "accepted_at": user.tos_accepted_at,
        "rejected_at": user.tos_rejected_at,
    }


def accept_tos(db: Session, user: models.User) -> dict:
    user.tos_accepted = 1
    user.tos_accepted_version = get_current_tos_version()
    user.tos_accepted_at = datetime.datetime.utcnow()
    user.tos_rejected_at = None
    db.commit()
    db.refresh(user)
    return get_tos_status(user)


def reject_tos(db: Session, user: models.User) -> dict:
    """El usuario retira su aceptación en cualquier momento. No borra
    tos_accepted_version/tos_accepted_at (historial de la última aceptación
    válida); solo apaga el flag y marca cuándo — get_current_user vuelve a
    bloquear todas las rutas salvo /api/auth y /api/tos en el próximo request."""
    user.tos_accepted = 0
    user.tos_rejected_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(user)
    return get_tos_status(user)
