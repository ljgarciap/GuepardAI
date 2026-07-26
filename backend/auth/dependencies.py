"""
dependencies.py — Dependencias de FastAPI para autenticación y autorización.

get_current_user / require_role / require_tenant_access son el punto único
que usa el retrofit de rutas existentes (B6-B8) para exigir auth y scoping
por tenant. check_login_rate_limit protege /api/auth/login.

Spec: docs/specs/autenticacion-multiusuario-multitenant.md
Design: docs/designs/autenticacion-multitenant-design.md §3.1, §3.5
"""
import os
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

import models
from database import get_db
from auth.security import decode_token
from auth.redis_client import get_redis_client

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

LOGIN_RATE_LIMIT_MAX_ATTEMPTS = int(os.getenv("LOGIN_RATE_LIMIT_MAX_ATTEMPTS", "5"))
LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "60"))


# Rutas que un usuario debe poder alcanzar incluso sin haber aceptado el ToS
# vigente: aceptarlo/rechazarlo (api/tos) y las operaciones de sesión
# (api/auth) — de lo contrario nadie podría llegar a la pantalla de
# aprobación ni cerrar sesión mientras está bloqueado.
TOS_EXEMPT_PATH_PREFIXES = ("/api/auth", "/api/tos")


def get_current_user(
    # Anotado como `Request` (no `Optional[Request]`): FastAPI solo reconoce e
    # inyecta el objeto Request especial cuando la anotación es exactamente
    # esa clase — envuelto en Optional/Union deja de detectarlo y en cambio
    # intenta generarle un schema Pydantic, lo que rompe TODAS las rutas que
    # dependen de get_current_user con un FastAPIError en el arranque. El
    # default None sigue permitiendo las llamadas directas de los tests
    # unitarios (sin request real) — ver TOS_EXEMPT_PATH_PREFIXES abajo.
    request: Request = None,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    try:
        payload = decode_token(token)
    except JWTError:
        raise credentials_exception
    if payload.get("type") != "access":
        raise credentials_exception
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if user is None or not user.is_active:
        raise credentials_exception

    # request es None solo en llamadas directas (tests unitarios) — ahí no hay
    # ruta HTTP real que eximir, así que el gate de ToS no aplica.
    if request is not None and not any(request.url.path.startswith(p) for p in TOS_EXEMPT_PATH_PREFIXES):
        from services.core import auth_service
        if not auth_service.has_accepted_current_tos(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="TOS_NOT_ACCEPTED")

    return user


def require_role(*roles: str):
    """Uso: Depends(require_role(UserRole.ADMIN.value, UserRole.SUPERADMIN.value))"""
    def checker(user: models.User = Depends(get_current_user)) -> models.User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user
    return checker


def check_brand_tenant_access(db: Session, user: models.User, brand_id: int) -> None:
    """
    Lógica compartida: ¿puede `user` operar sobre el Brand `brand_id`?
    Usada tanto por `require_tenant_access` (brand_id en el path) como por
    rutas donde brand_id llega en el body/form (no resoluble como Depends).

    `superadmin` es un bypass EXPLÍCITO por rol — nunca implícito por
    `tenant_id IS NULL` incidental (ese caso es de un Brand aún no alineado,
    no de un superadmin, y debe seguir denegado a admin/cliente).
    """
    if user.role == models.UserRole.SUPERADMIN.value:
        return
    brand = db.query(models.Brand).filter(models.Brand.id == brand_id).first()
    if brand is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
    if brand.tenant_id is None or brand.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Brand belongs to a different tenant")


def require_tenant_access(
    brand_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> models.User:
    """Verifica que `user` pueda operar sobre el Brand `brand_id` (path/query param)."""
    check_brand_tenant_access(db, user, brand_id)
    return user


def check_job_tenant_access(db: Session, user: models.User, job) -> None:
    """
    Igual que check_brand_tenant_access pero a partir de un job ya cargado
    por la ruta (GenerationJob o TemplateMergeJob, ambos con `brand_id` y
    `owner_id`). `job=None` se trata como 404 — el caller ya hizo el query,
    esto solo decide si el resultado (existente o no) es visible para `user`.

    El owner del job siempre tiene acceso, incluso si `brand_id` es NULL o
    quedó desalineado con su tenant actual (mismo fallback ya usado ad-hoc en
    collaborators.py/reviews.py, centralizado acá).
    """
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if user.role == models.UserRole.SUPERADMIN.value:
        return
    if getattr(job, "owner_id", None) is not None and job.owner_id == user.id:
        return
    brand = db.query(models.Brand).filter(models.Brand.id == job.brand_id).first() if job.brand_id else None
    if brand is None or brand.tenant_id is None or brand.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Job belongs to a different tenant")


def tenant_brand_ids_filter(db: Session, user: models.User):
    """
    Para rutas de LISTADO: subquery de IDs de Brand del tenant del usuario,
    o None si no corresponde filtrar (superadmin ve todo). Uso:
    `if ids is not None: query = query.filter(Model.brand_id.in_(ids))`
    """
    if user.role == models.UserRole.SUPERADMIN.value:
        return None
    return db.query(models.Brand.id).filter(models.Brand.tenant_id == user.tenant_id)


def check_login_rate_limit(request: Request, email: str) -> None:
    """
    Ventana deslizante simple en Redis por (ip, email). Se llama ANTES de
    comparar la password (evita gastar un ciclo de bcrypt en un request que
    ya va a ser rechazado).

    Fail-open ante caída de Redis: una caída de infraestructura no debe
    bloquear TODOS los logins de la plataforma; el refresh/logout (que sí
    dependen de Redis para revocación) fallan explícito en cambio (B4).
    """
    client_ip = request.client.host if request.client else "unknown"
    key = f"login_attempts:{client_ip}:{email}"
    try:
        r = get_redis_client()
        attempts = r.incr(key)
        if attempts == 1:
            r.expire(key, LOGIN_RATE_LIMIT_WINDOW_SECONDS)
    except Exception:
        return
    if attempts > LOGIN_RATE_LIMIT_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
        )
