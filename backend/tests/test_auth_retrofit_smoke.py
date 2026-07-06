"""
test_auth_retrofit_smoke.py — Ninguna ruta existente quedó sin exigir auth (B6).

No revalida el comportamiento de cada ruta (eso ya lo cubren sus tests
propios, ahora actualizados con superadmin_headers) — solo confirma que un
request SIN token recibe 401 en todo el mapa de rutas de main.py, incluidas
las de Admin (que además exigen rol superadmin). Sirve de red de seguridad
contra una ruta nueva que se agregue sin `Depends(get_current_user)`.

Spec: docs/specs/autenticacion-multiusuario-multitenant.md
Design: docs/designs/autenticacion-multitenant-design.md §3.3
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(db_session):
    from main import app, get_db
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# (método, path) — un representante por tag; 404/422 de la ruta en sí no
# importa acá, solo que el gate de auth corra ANTES de esa lógica (401).
ROUTES_REQUIRING_AUTH = [
    ("GET", "/api/brands"),
    ("POST", "/api/brands"),
    ("PUT", "/api/brands/1"),
    ("GET", "/api/footers"),
    ("POST", "/api/footers"),
    ("PUT", "/api/footers/1/select"),
    ("DELETE", "/api/footers/1"),
    ("PUT", "/api/footers/toggle?enabled=true"),
    ("GET", "/api/library/images"),
    ("GET", "/api/generation/status/1"),
    ("GET", "/api/generation/download/1"),
    ("POST", "/api/brand/upload"),
    ("GET", "/api/ingestion/status/x"),
    ("GET", "/api/library/blueprints"),
    ("GET", "/api/library/knowledge"),
    ("GET", "/api/library/portfolios"),
    ("PATCH", "/api/library/portfolios/1"),
    ("DELETE", "/api/library/portfolios/1"),
    ("GET", "/api/available-styles"),
    ("GET", "/api/available-knowledge"),
    ("GET", "/api/available-dialects"),
    ("POST", "/api/presentations/generate"),
    ("GET", "/api/presentations/1/slides"),
    ("PUT", "/api/presentations/1/slides/1"),
    ("POST", "/api/presentations/1/resume"),
    ("POST", "/api/presentations/1/feedback"),
    ("GET", "/api/presentations/1/feedback"),
    ("GET", "/api/admin/metrics"),
    ("DELETE", "/api/admin/reset-db"),
    ("POST", "/api/template-merge/upload-template"),
    ("POST", "/api/template-merge/jobs"),
    ("GET", "/api/template-merge/jobs/1"),
    ("GET", "/api/template-merge/jobs/1/download"),
    ("GET", "/api/template-merge/templates"),
    ("POST", "/api/users"),
    ("GET", "/api/users"),
    ("PATCH", "/api/users/1/deactivate"),
]


@pytest.mark.integration
@pytest.mark.parametrize("method,path", ROUTES_REQUIRING_AUTH)
def test_route_without_token_returns_401(client, method, path):
    resp = client.request(method, path)
    assert resp.status_code == 401, f"{method} {path} returned {resp.status_code}, expected 401 (no token)"
