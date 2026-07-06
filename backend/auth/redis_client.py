"""
redis_client.py — Cliente Redis compartido del módulo de auth.

Usado para: revocación/rotación de refresh tokens (auth_service.py) y rate
limiting de login (dependencies.py). Redis ya es dependencia dura del
proyecto (broker de Celery), así que esto no agrega infraestructura nueva.

Spec: docs/specs/autenticacion-multiusuario-multitenant.md
Design: docs/designs/autenticacion-multitenant-design.md §2.4
"""
import os

import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

_client: "redis.Redis | None" = None


def get_redis_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    return _client
