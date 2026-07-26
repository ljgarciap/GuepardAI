"""
test_auth_routes.py — /api/auth/register, /login, /refresh, /logout, /me (B4).

Spec: docs/specs/autenticacion-multiusuario-multitenant.md
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import models


@pytest.fixture()
def client(db_session):
    from main import app, get_db
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _register(client, email="new.admin@example.com", password="a-strong-password", tenant_name=None):
    body = {"email": email, "password": password}
    if tenant_name:
        body["tenant_name"] = tenant_name
    return client.post("/api/auth/register", json=body)


@pytest.mark.integration
class TestRegister:

    def test_register_creates_tenant_and_admin_returns_tokens(self, client, db_session):
        resp = _register(client, email="founder@acme.com", tenant_name="Acme Co")

        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data and "refresh_token" in data

        user = db_session.query(models.User).filter(models.User.email == "founder@acme.com").first()
        assert user is not None
        assert user.role == models.UserRole.ADMIN.value
        assert user.tenant_id is not None
        tenant = db_session.query(models.Tenant).get(user.tenant_id)
        assert tenant.name == "Acme Co"

    def test_duplicate_email_returns_409(self, client):
        _register(client, email="dup@example.com")
        resp = _register(client, email="dup@example.com")

        assert resp.status_code == 409

    def test_duplicate_email_race_returns_409_not_500(self, db_session):
        """
        Senior Reviewer #5: si el pre-check SELECT no ve una fila que ya
        existe (carrera entre dos registros concurrentes), el unique
        constraint de la DB debe seguir devolviendo 409, no un 500 crudo.
        Se simula la carrera forzando Query.first() a devolver None mientras
        el email ya está comprometido de verdad en la base.
        """
        from sqlalchemy.orm import Query
        from fastapi import HTTPException
        from auth import security as security_module
        from services.core import auth_service

        existing_user = models.User(
            email="race@example.com",
            hashed_password=security_module.hash_password("irrelevant-password"),
            role=models.UserRole.ADMIN.value,
            tenant_id=None,
            is_active=1,
        )
        db_session.add(existing_user)
        db_session.commit()

        with patch.object(Query, "first", return_value=None):
            with pytest.raises(HTTPException) as exc:
                auth_service.register_user(db_session, "race@example.com", "a-strong-password")

        assert exc.value.status_code == 409

    def test_weak_password_returns_422(self, client):
        resp = client.post("/api/auth/register", json={"email": "weak@example.com", "password": "short"})
        assert resp.status_code == 422


@pytest.mark.integration
class TestLogin:

    def test_valid_credentials_returns_tokens(self, client):
        _register(client, email="login.ok@example.com", password="a-strong-password")

        resp = client.post("/api/auth/login", json={"email": "login.ok@example.com", "password": "a-strong-password"})

        assert resp.status_code == 200
        assert "access_token" in resp.json() and "refresh_token" in resp.json()

    def test_wrong_password_returns_401_generic(self, client):
        _register(client, email="login.wrong@example.com", password="a-strong-password")

        resp = client.post("/api/auth/login", json={"email": "login.wrong@example.com", "password": "nope-nope"})

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Incorrect email or password"

    def test_nonexistent_email_returns_same_generic_401(self, client):
        resp = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "whatever123"})

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Incorrect email or password"

    def test_nonexistent_email_still_runs_password_hash_check(self, client, monkeypatch):
        """
        Cierra el timing side-channel (Senior Reviewer, blocker #1): si el
        email no existe, authenticate_user debe igual llamar
        verify_password (contra un hash dummy) para que el costo de CPU sea
        el mismo que cuando el email existe con password incorrecta.
        """
        from auth import security
        calls = []
        original_verify = security.verify_password

        def spy(*args, **kwargs):
            calls.append(1)
            return original_verify(*args, **kwargs)

        monkeypatch.setattr(security, "verify_password", spy)

        client.post("/api/auth/login", json={"email": "ghost-timing@example.com", "password": "whatever123"})

        assert len(calls) == 1

    def test_rate_limit_exceeded_returns_429(self, client, monkeypatch):
        fake_redis = MagicMock()
        fake_redis.incr.return_value = 999
        monkeypatch.setattr("auth.dependencies.get_redis_client", lambda: fake_redis)

        resp = client.post("/api/auth/login", json={"email": "anyone@example.com", "password": "whatever123"})

        assert resp.status_code == 429


@pytest.mark.integration
class TestRefreshAndLogout:

    def test_refresh_returns_new_tokens(self, client):
        tokens = _register(client, email="refresh.ok@example.com").json()

        resp = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

        assert resp.status_code == 200
        new_tokens = resp.json()
        assert new_tokens["refresh_token"] != tokens["refresh_token"]

    def test_reusing_rotated_refresh_token_returns_401(self, client):
        tokens = _register(client, email="replay@example.com").json()
        client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

        # El refresh original ya fue rotado (invalidado) por la llamada anterior
        resp = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

        assert resp.status_code == 401

    def test_logout_then_refresh_returns_401(self, client):
        tokens = _register(client, email="logout.ok@example.com").json()

        logout_resp = client.post("/api/auth/logout", json={"refresh_token": tokens["refresh_token"]})
        assert logout_resp.status_code == 204

        resp = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert resp.status_code == 401

    def test_garbage_refresh_token_returns_401(self, client):
        resp = client.post("/api/auth/refresh", json={"refresh_token": "not-a-real-token"})
        assert resp.status_code == 401


@pytest.mark.integration
class TestMe:

    def test_returns_current_user_with_valid_token(self, client):
        tokens = _register(client, email="me.ok@example.com").json()

        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "me.ok@example.com"
        assert data["role"] == models.UserRole.ADMIN.value
        assert "hashed_password" not in data

    def test_no_token_returns_401(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401


@pytest.mark.integration
class TestChangePassword:

    def test_correct_current_password_changes_it(self, client):
        tokens = _register(client, email="changepw.ok@example.com", password="original-password").json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        resp = client.post("/api/auth/change-password", json={
            "current_password": "original-password", "new_password": "brand-new-password",
        }, headers=headers)
        assert resp.status_code == 204

        old_login = client.post("/api/auth/login", json={"email": "changepw.ok@example.com", "password": "original-password"})
        assert old_login.status_code == 401

        new_login = client.post("/api/auth/login", json={"email": "changepw.ok@example.com", "password": "brand-new-password"})
        assert new_login.status_code == 200

    def test_wrong_current_password_returns_400(self, client):
        tokens = _register(client, email="changepw.wrong@example.com", password="original-password").json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        resp = client.post("/api/auth/change-password", json={
            "current_password": "not-the-real-password", "new_password": "brand-new-password",
        }, headers=headers)

        assert resp.status_code == 400

    def test_weak_new_password_returns_422(self, client):
        tokens = _register(client, email="changepw.weak@example.com", password="original-password").json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        resp = client.post("/api/auth/change-password", json={
            "current_password": "original-password", "new_password": "short",
        }, headers=headers)

        assert resp.status_code == 422

    def test_no_token_returns_401(self, client):
        resp = client.post("/api/auth/change-password", json={
            "current_password": "whatever", "new_password": "brand-new-password",
        })
        assert resp.status_code == 401
