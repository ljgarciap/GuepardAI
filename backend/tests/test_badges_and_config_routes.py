"""
test_badges_and_config_routes.py — /api/users/me/badges (ítem 8),
/api/config/prompt-intents y /api/library/portfolios/{job_id} detail
(soporte-indicaciones).

Spec: docs/specs/reviews-analitica-colaboracion.md, docs/specs/soporte-indicaciones.md
"""
import json
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


def _make_brand(db, tenant_id=None):
    brand = models.Brand(name=f"Brand_{uuid.uuid4().hex}", tenant_id=tenant_id)
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


def _make_job(db, brand_id, owner_id=None, prompt="test", pptx_path=None):
    job = models.GenerationJob(brand_id=brand_id, owner_id=owner_id, prompt=prompt, pptx_path=pptx_path, status=models.GenerationJobStatus.COMPLETED)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _headers(user):
    token = security.create_access_token(user.id, user.role, user.tenant_id)
    return {"Authorization": f"Bearer {token}"}


def _set_config(db, key, value):
    cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if cfg is None:
        db.add(models.SystemConfig(key=key, value=value))
    else:
        cfg.value = value
    db.commit()


@pytest.mark.integration
class TestMyBadges:

    def test_zero_presentations_no_badge_yet(self, client, db_session):
        tenant = _make_tenant(db_session)
        user = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)

        resp = client.get("/api/users/me/badges", headers=_headers(user))
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 0
        assert body["current_badge"] is None
        assert body["next_badge"]["threshold"] == 5

    def test_exactly_at_threshold_unlocks_badge(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        user = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        for _ in range(5):
            _make_job(db_session, brand.id, owner_id=user.id)

        resp = client.get("/api/users/me/badges", headers=_headers(user))
        body = resp.json()
        assert body["count"] == 5
        assert body["current_badge"]["label"] == "Starter"
        assert body["next_badge"]["label"] == "Expert"
        assert body["progress_to_next"] == 0.0

    def test_between_thresholds_computes_progress(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        user = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        for _ in range(7):  # a mitad de camino entre 5 (Starter) y 10 (Expert)
            _make_job(db_session, brand.id, owner_id=user.id)

        resp = client.get("/api/users/me/badges", headers=_headers(user))
        body = resp.json()
        assert body["current_badge"]["label"] == "Starter"
        assert body["next_badge"]["label"] == "Expert"
        assert body["progress_to_next"] == 0.4  # (7-5)/(10-5)

    def test_at_top_tier_has_no_next_badge(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        user = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        for _ in range(25):
            _make_job(db_session, brand.id, owner_id=user.id)

        resp = client.get("/api/users/me/badges", headers=_headers(user))
        body = resp.json()
        assert body["current_badge"]["label"] == "Genius"
        assert body["next_badge"] is None
        assert body["progress_to_next"] is None

    def test_other_users_presentations_not_counted(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        user = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        other = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        _make_job(db_session, brand.id, owner_id=other.id)
        _make_job(db_session, brand.id, owner_id=other.id)

        resp = client.get("/api/users/me/badges", headers=_headers(user))
        assert resp.json()["count"] == 0

    def test_custom_thresholds_from_system_config(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        user = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        _set_config(db_session, "badge_thresholds_v1", json.dumps([{"threshold": 1, "label": "First"}]))
        _make_job(db_session, brand.id, owner_id=user.id)

        resp = client.get("/api/users/me/badges", headers=_headers(user))
        assert resp.json()["current_badge"]["label"] == "First"


@pytest.mark.integration
class TestPromptIntents:

    def test_returns_empty_list_when_not_seeded(self, client, db_session):
        tenant = _make_tenant(db_session)
        user = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)

        resp = client.get("/api/config/prompt-intents", headers=_headers(user))
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_returns_seeded_value(self, client, db_session):
        tenant = _make_tenant(db_session)
        user = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        _set_config(db_session, "intent_library_v1", json.dumps([{"slug": "test_intent", "label": "Test"}]))

        resp = client.get("/api/config/prompt-intents", headers=_headers(user))
        assert resp.status_code == 200
        slugs = [i["slug"] for i in resp.json()]
        assert "test_intent" in slugs

    def test_any_authenticated_role_can_read(self, client, db_session):
        tenant = _make_tenant(db_session)
        cliente = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)

        resp = client.get("/api/config/prompt-intents", headers=_headers(cliente))
        assert resp.status_code == 200


@pytest.mark.integration
class TestPortfolioDetail:

    def test_detail_includes_prompt_and_metadata(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id, prompt="Reusable prompt text")
        job.prompt_metadata = {"objective": "test"}
        db_session.commit()

        resp = client.get(f"/api/library/portfolios/{job.id}", headers=_headers(owner))
        assert resp.status_code == 200
        body = resp.json()
        assert body["prompt"] == "Reusable prompt text"
        assert body["prompt_metadata"] == {"objective": "test"}

    def test_404_when_job_has_no_prompt(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id, prompt=None)

        resp = client.get(f"/api/library/portfolios/{job.id}", headers=_headers(owner))
        assert resp.status_code == 404

    def test_cross_tenant_forbidden(self, client, db_session):
        tenant = _make_tenant(db_session, "Home")
        other_tenant = _make_tenant(db_session, "Other")
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        outsider = _make_user(db_session, models.UserRole.CLIENTE.value, other_tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id, prompt="secret prompt")

        resp = client.get(f"/api/library/portfolios/{job.id}", headers=_headers(outsider))
        assert resp.status_code == 403
