"""
test_tenants_routes.py — /api/admin/tenants (alta y listado de Tenants por el superadmin).

Spec: docs/specs/gestion-tenants-superadmin.md
"""
import uuid

import pytest
from fastapi.testclient import TestClient

import models
from auth import security


@pytest.fixture()
def client(db_session):
    from main import app, get_db
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _make_tenant(db, name="Tenant"):
    tenant = models.Tenant(name=f"{name}_{uuid.uuid4().hex}")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def _make_user(db, role, tenant_id=None, email=None):
    user = models.User(
        email=email or f"{role}_{uuid.uuid4().hex}@example.com",
        hashed_password=security.hash_password("irrelevant-password"),
        role=role,
        tenant_id=tenant_id,
        is_active=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers(user):
    token = security.create_access_token(user.id, user.role, user.tenant_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
class TestCreateTenant:

    def test_superadmin_creates_tenant_and_admin(self, client, db_session, superadmin_headers):
        resp = client.post(
            "/api/admin/tenants",
            json={"name": "Acme Corp", "admin_email": "acme.admin@example.com", "admin_password": "supersecret1"},
            headers=superadmin_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["tenant"]["name"] == "Acme Corp"
        assert body["admin"]["email"] == "acme.admin@example.com"

        created_admin = db_session.query(models.User).filter(models.User.email == "acme.admin@example.com").first()
        assert created_admin.role == models.UserRole.ADMIN.value
        assert created_admin.tenant_id == body["tenant"]["id"]

    def test_admin_forbidden(self, client, db_session):
        tenant = _make_tenant(db_session)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)

        resp = client.post(
            "/api/admin/tenants",
            json={"name": "Nope Corp", "admin_email": "nope.admin@example.com", "admin_password": "supersecret1"},
            headers=_headers(admin),
        )
        assert resp.status_code == 403

    def test_cliente_forbidden(self, client, db_session):
        tenant = _make_tenant(db_session)
        cliente = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)

        resp = client.post(
            "/api/admin/tenants",
            json={"name": "Nope Corp", "admin_email": "nope.admin2@example.com", "admin_password": "supersecret1"},
            headers=_headers(cliente),
        )
        assert resp.status_code == 403

    def test_duplicate_admin_email_conflicts(self, client, db_session, superadmin_headers):
        tenant = _make_tenant(db_session)
        _make_user(db_session, models.UserRole.ADMIN.value, tenant.id, email="taken@example.com")

        resp = client.post(
            "/api/admin/tenants",
            json={"name": "Dup Corp", "admin_email": "taken@example.com", "admin_password": "supersecret1"},
            headers=superadmin_headers,
        )
        assert resp.status_code == 409

    def test_short_password_rejected(self, client, db_session, superadmin_headers):
        resp = client.post(
            "/api/admin/tenants",
            json={"name": "Short Corp", "admin_email": "short.pw@example.com", "admin_password": "short"},
            headers=superadmin_headers,
        )
        assert resp.status_code == 422


@pytest.mark.integration
class TestListTenants:

    def test_superadmin_sees_all_tenants(self, client, db_session, superadmin_headers):
        tenant_a = _make_tenant(db_session, "ListA")
        tenant_b = _make_tenant(db_session, "ListB")

        resp = client.get("/api/admin/tenants", headers=superadmin_headers)
        assert resp.status_code == 200
        names = {t["name"] for t in resp.json()}
        assert tenant_a.name in names
        assert tenant_b.name in names

    def test_admin_forbidden(self, client, db_session):
        tenant = _make_tenant(db_session)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)

        resp = client.get("/api/admin/tenants", headers=_headers(admin))
        assert resp.status_code == 403
