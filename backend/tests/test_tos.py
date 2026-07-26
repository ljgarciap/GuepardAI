"""
test_tos.py — /api/tos/status, /accept, /reject and the ToS gate inside
get_current_user (auth/dependencies.py).

Spec: docs/designs/claude-skills-benchmark-and-team-feedback-2026-07.md §5
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


def _register(client, email="tos.user@example.com", password="a-strong-password"):
    resp = client.post("/api/auth/register", json={"email": email, "password": password})
    return resp.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _make_superadmin(db, email="tos.super@example.com"):
    user = models.User(
        email=email,
        hashed_password=security.hash_password("irrelevant-password"),
        role=models.UserRole.SUPERADMIN.value,
        tenant_id=None,
        is_active=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = security.create_access_token(user.id, user.role, user.tenant_id)
    return user, token


@pytest.mark.integration
class TestTosStatus:

    def test_new_user_defaults_to_not_accepted(self, client):
        token = _register(client)
        resp = client.get("/api/tos/status", headers=_auth_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] is False
        assert data["current_version"]
        assert data["accepted_version"] is None

    def test_superadmin_is_always_accepted(self, db_session, client):
        _user, token = _make_superadmin(db_session)
        resp = client.get("/api/tos/status", headers=_auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["accepted"] is True


@pytest.mark.integration
class TestTosGateOnProtectedRoutes:

    def test_protected_route_blocked_before_accepting(self, client):
        token = _register(client, email="tos.blocked@example.com")
        resp = client.get("/api/available-dialects", headers=_auth_headers(token))
        assert resp.status_code == 403
        assert resp.json()["detail"] == "TOS_NOT_ACCEPTED"

    def test_protected_route_allowed_after_accepting(self, client):
        token = _register(client, email="tos.accepted@example.com")
        client.post("/api/tos/accept", headers=_auth_headers(token))

        resp = client.get("/api/available-dialects", headers=_auth_headers(token))

        assert resp.status_code == 200

    def test_auth_me_reachable_even_when_not_accepted(self, client):
        """/api/auth/* stays reachable regardless of ToS state — otherwise a
        blocked user could never log out or refresh their session."""
        token = _register(client, email="tos.stillauth@example.com")
        resp = client.get("/api/auth/me", headers=_auth_headers(token))
        assert resp.status_code == 200

    def test_rejecting_revokes_access_again(self, client):
        token = _register(client, email="tos.reject@example.com")
        client.post("/api/tos/accept", headers=_auth_headers(token))
        assert client.get("/api/available-dialects", headers=_auth_headers(token)).status_code == 200

        reject_resp = client.post("/api/tos/reject", headers=_auth_headers(token))
        assert reject_resp.status_code == 200
        assert reject_resp.json()["accepted"] is False

        blocked_resp = client.get("/api/available-dialects", headers=_auth_headers(token))
        assert blocked_resp.status_code == 403
        assert blocked_resp.json()["detail"] == "TOS_NOT_ACCEPTED"

        # /api/tos/* itself stays reachable so the user can re-accept
        status_resp = client.get("/api/tos/status", headers=_auth_headers(token))
        assert status_resp.status_code == 200
        assert status_resp.json()["accepted"] is False

    def test_superadmin_bypasses_gate_without_accepting(self, db_session, client):
        _user, token = _make_superadmin(db_session)
        resp = client.get("/api/available-dialects", headers=_auth_headers(token))
        assert resp.status_code == 200


@pytest.mark.integration
class TestTosVersionMismatchReblocks:

    def test_stale_accepted_version_is_treated_as_not_accepted(self, db_session, client, monkeypatch):
        token = _register(client, email="tos.stale@example.com")
        client.post("/api/tos/accept", headers=_auth_headers(token))
        assert client.get("/api/available-dialects", headers=_auth_headers(token)).status_code == 200

        # Simula un bump de versión del ToS (seed.py: tos_current_version) sin
        # que el usuario haya vuelto a aceptar — debe quedar bloqueado otra vez.
        from services.core import auth_service
        monkeypatch.setattr(auth_service, "get_current_tos_version", lambda: "2.0")

        resp = client.get("/api/available-dialects", headers=_auth_headers(token))
        assert resp.status_code == 403
        assert resp.json()["detail"] == "TOS_NOT_ACCEPTED"
