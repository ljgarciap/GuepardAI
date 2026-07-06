"""
test_users_routes.py — /api/users: alta/listado/desactivación de `cliente` (B5).

Spec: docs/specs/autenticacion-multiusuario-multitenant.md
"""
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


def _make_user(db, role, tenant_id=None, email=None, is_active=1):
    user = models.User(
        email=email or f"{role}_{id(object())}@example.com",
        hashed_password=security.hash_password("irrelevant-password"),
        role=role,
        tenant_id=tenant_id,
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_headers(user):
    token = security.create_access_token(user.id, user.role, user.tenant_id)
    return {"Authorization": f"Bearer {token}"}


def _make_tenant(db, name="Test Tenant"):
    tenant = models.Tenant(name=name)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


@pytest.mark.integration
class TestCreateUser:

    def test_admin_creates_cliente_in_own_tenant(self, client, db_session):
        tenant = _make_tenant(db_session)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant_id=tenant.id)

        resp = client.post(
            "/api/users",
            json={"email": "new.cliente@example.com", "password": "a-strong-password"},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["role"] == models.UserRole.CLIENTE.value
        assert data["tenant_id"] == tenant.id

    def test_admin_cannot_target_another_tenant_via_payload(self, client, db_session):
        tenant = _make_tenant(db_session, "Admin Tenant")
        other_tenant = _make_tenant(db_session, "Other Tenant")
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant_id=tenant.id)

        resp = client.post(
            "/api/users",
            json={"email": "sneaky@example.com", "password": "a-strong-password", "tenant_id": other_tenant.id},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 201
        assert resp.json()["tenant_id"] == tenant.id  # ignorado: siempre el propio tenant del admin

    def test_cliente_cannot_create_users(self, client, db_session):
        tenant = _make_tenant(db_session)
        cliente = _make_user(db_session, models.UserRole.CLIENTE.value, tenant_id=tenant.id)

        resp = client.post(
            "/api/users",
            json={"email": "someone@example.com", "password": "a-strong-password"},
            headers=_auth_headers(cliente),
        )

        assert resp.status_code == 403

    def test_duplicate_email_returns_409(self, client, db_session):
        tenant = _make_tenant(db_session)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant_id=tenant.id)
        _make_user(db_session, models.UserRole.CLIENTE.value, tenant_id=tenant.id, email="dup.user@example.com")

        resp = client.post(
            "/api/users",
            json={"email": "dup.user@example.com", "password": "a-strong-password"},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 409

    def test_superadmin_creates_user_in_specified_tenant(self, client, db_session):
        target_tenant = _make_tenant(db_session, "Target Tenant")
        superadmin = _make_user(db_session, models.UserRole.SUPERADMIN.value, tenant_id=None)

        resp = client.post(
            "/api/users",
            json={"email": "cross.tenant@example.com", "password": "a-strong-password", "tenant_id": target_tenant.id},
            headers=_auth_headers(superadmin),
        )

        assert resp.status_code == 201
        assert resp.json()["tenant_id"] == target_tenant.id


@pytest.mark.integration
class TestListUsers:

    def test_admin_sees_only_own_tenant(self, client, db_session):
        tenant_a = _make_tenant(db_session, "Tenant A")
        tenant_b = _make_tenant(db_session, "Tenant B")
        admin_a = _make_user(db_session, models.UserRole.ADMIN.value, tenant_id=tenant_a.id)
        _make_user(db_session, models.UserRole.CLIENTE.value, tenant_id=tenant_a.id, email="a.cliente@example.com")
        _make_user(db_session, models.UserRole.CLIENTE.value, tenant_id=tenant_b.id, email="b.cliente@example.com")

        resp = client.get("/api/users", headers=_auth_headers(admin_a))

        assert resp.status_code == 200
        emails = {u["email"] for u in resp.json()}
        assert "a.cliente@example.com" in emails
        assert "b.cliente@example.com" not in emails

    def test_superadmin_sees_all_tenants(self, client, db_session):
        tenant_a = _make_tenant(db_session, "Tenant A2")
        tenant_b = _make_tenant(db_session, "Tenant B2")
        superadmin = _make_user(db_session, models.UserRole.SUPERADMIN.value, tenant_id=None)
        _make_user(db_session, models.UserRole.CLIENTE.value, tenant_id=tenant_a.id, email="a2.cliente@example.com")
        _make_user(db_session, models.UserRole.CLIENTE.value, tenant_id=tenant_b.id, email="b2.cliente@example.com")

        resp = client.get("/api/users", headers=_auth_headers(superadmin))

        emails = {u["email"] for u in resp.json()}
        assert "a2.cliente@example.com" in emails
        assert "b2.cliente@example.com" in emails


@pytest.mark.integration
class TestDeactivateUser:

    def test_admin_deactivates_own_tenant_user(self, client, db_session):
        tenant = _make_tenant(db_session)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant_id=tenant.id)
        cliente = _make_user(db_session, models.UserRole.CLIENTE.value, tenant_id=tenant.id)

        resp = client.patch(f"/api/users/{cliente.id}/deactivate", headers=_auth_headers(admin))

        assert resp.status_code == 200
        assert resp.json()["is_active"] == 0

    def test_admin_cannot_deactivate_other_tenant_user(self, client, db_session):
        tenant_a = _make_tenant(db_session, "Tenant A3")
        tenant_b = _make_tenant(db_session, "Tenant B3")
        admin_a = _make_user(db_session, models.UserRole.ADMIN.value, tenant_id=tenant_a.id)
        cliente_b = _make_user(db_session, models.UserRole.CLIENTE.value, tenant_id=tenant_b.id)

        resp = client.patch(f"/api/users/{cliente_b.id}/deactivate", headers=_auth_headers(admin_a))

        assert resp.status_code == 403

    def test_deactivate_nonexistent_user_returns_404(self, client, db_session):
        tenant = _make_tenant(db_session)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant_id=tenant.id)

        resp = client.patch("/api/users/999999/deactivate", headers=_auth_headers(admin))

        assert resp.status_code == 404
