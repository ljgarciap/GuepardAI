"""
security.py — Password hashing y JWT encode/decode.

Access token: stateless, TTL corto (JWT_ACCESS_TOKEN_TTL_MINUTES).
Refresh token: TTL largo (JWT_REFRESH_TOKEN_TTL_DAYS); su jti se guarda en
Redis (ver dependencies.py / auth_service.py) para poder revocarlo — este
módulo solo genera y decodifica el JWT, no conoce Redis.

Spec: docs/specs/autenticacion-multiusuario-multitenant.md
Design: docs/designs/autenticacion-multitenant-design.md §2.4, §3.1
"""
import datetime
import os
import uuid
from typing import Optional, Tuple

from jose import jwt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    # No hay un default seguro posible para un secreto de firma: si este
    # módulo cayera en un valor hardcodeado, cualquiera que lea el repo
    # público podría forjar un token válido para cualquier user_id/rol,
    # incluido superadmin (Senior Reviewer, blocker #2, 2026-07-05).
    # Falla el arranque en vez de firmar tokens con un secreto conocido.
    raise RuntimeError(
        "JWT_SECRET_KEY no está configurado. Es un secreto de firma JWT — no "
        "existe un valor por defecto seguro. Configuralo en .env (o .env.test "
        "para tests) antes de arrancar el backend."
    )
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_TTL_MINUTES", "15"))
REFRESH_TOKEN_TTL_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_TTL_DAYS", "7"))


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: int, role: str, tenant_id: Optional[int]) -> str:
    now = datetime.datetime.utcnow()
    payload = {
        "sub": str(user_id),
        "role": role,
        "tenant_id": tenant_id,
        "type": "access",
        "iat": now,
        "exp": now + datetime.timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: int) -> Tuple[str, str, datetime.datetime]:
    """Devuelve (token, jti, expires_at). El caller guarda jti->user_id en Redis con TTL."""
    jti = uuid.uuid4().hex
    now = datetime.datetime.utcnow()
    expires_at = now + datetime.timedelta(days=REFRESH_TOKEN_TTL_DAYS)
    payload = {
        "sub": str(user_id),
        "jti": jti,
        "type": "refresh",
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token, jti, expires_at


def decode_token(token: str) -> dict:
    """Lanza jose.JWTError si el token es inválido, expiró o fue manipulado."""
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
