"""
test_collaborators_routes.py — /api/presentations/{job_id}/collaborators
(reviews-analitica-colaboracion, ítem 1).

Spec: docs/specs/reviews-analitica-colaboracion.md
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


def _make_brand(db, tenant_id=None):
    brand = models.Brand(name=f"Brand_{uuid.uuid4().hex}", tenant_id=tenant_id)
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


def _make_job(db, brand_id, owner_id=None):
    job = models.GenerationJob(brand_id=brand_id, owner_id=owner_id, prompt="test", status=models.GenerationJobStatus.COMPLETED)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _headers(user):
    token = security.create_access_token(user.id, user.role, user.tenant_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
class TestAddCollaborator:

    def test_owner_can_add_collaborator(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        target = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)

        resp = client.post(f"/api/presentations/{job.id}/collaborators", json={"user_id": target.id}, headers=_headers(owner))
        assert resp.status_code == 200
        assert resp.json()["user_id"] == target.id

        row = db_session.query(models.GenerationJobCollaborator).filter(
            models.GenerationJobCollaborator.job_id == job.id, models.GenerationJobCollaborator.user_id == target.id
        ).first()
        assert row is not None

    def test_tenant_admin_can_add_collaborator(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)
        target = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)

        resp = client.post(f"/api/presentations/{job.id}/collaborators", json={"user_id": target.id}, headers=_headers(admin))
        assert resp.status_code == 200

    def test_non_owner_non_admin_forbidden(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        stranger = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        target = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)

        resp = client.post(f"/api/presentations/{job.id}/collaborators", json={"user_id": target.id}, headers=_headers(stranger))
        assert resp.status_code == 403

    def test_target_user_from_different_tenant_rejected(self, client, db_session):
        tenant = _make_tenant(db_session, "Home")
        other_tenant = _make_tenant(db_session, "Other")
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        outsider = _make_user(db_session, models.UserRole.CLIENTE.value, other_tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)

        resp = client.post(f"/api/presentations/{job.id}/collaborators", json={"user_id": outsider.id}, headers=_headers(owner))
        assert resp.status_code == 403

    def test_job_without_brand_rejects_any_collaborator(self, client, db_session):
        tenant = _make_tenant(db_session)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        target = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand_id=None, owner_id=owner.id)

        resp = client.post(f"/api/presentations/{job.id}/collaborators", json={"user_id": target.id}, headers=_headers(owner))
        assert resp.status_code == 403

    def test_nonexistent_target_user_404(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)

        resp = client.post(f"/api/presentations/{job.id}/collaborators", json={"user_id": 999999}, headers=_headers(owner))
        assert resp.status_code == 404

    def test_adding_same_collaborator_twice_is_idempotent(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        target = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)

        client.post(f"/api/presentations/{job.id}/collaborators", json={"user_id": target.id}, headers=_headers(owner))
        resp = client.post(f"/api/presentations/{job.id}/collaborators", json={"user_id": target.id}, headers=_headers(owner))
        assert resp.status_code == 200

        count = db_session.query(models.GenerationJobCollaborator).filter(
            models.GenerationJobCollaborator.job_id == job.id
        ).count()
        assert count == 1


@pytest.mark.integration
class TestRemoveCollaborator:

    def test_owner_can_remove_collaborator(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        target = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)
        db_session.add(models.GenerationJobCollaborator(job_id=job.id, user_id=target.id))
        db_session.commit()

        resp = client.delete(f"/api/presentations/{job.id}/collaborators/{target.id}", headers=_headers(owner))
        assert resp.status_code == 200

        remaining = db_session.query(models.GenerationJobCollaborator).filter(
            models.GenerationJobCollaborator.job_id == job.id
        ).count()
        assert remaining == 0

    def test_remove_nonexistent_collaborator_404(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)

        resp = client.delete(f"/api/presentations/{job.id}/collaborators/999999", headers=_headers(owner))
        assert resp.status_code == 404

    def test_stranger_cannot_remove_collaborator(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        target = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        stranger = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)
        db_session.add(models.GenerationJobCollaborator(job_id=job.id, user_id=target.id))
        db_session.commit()

        resp = client.delete(f"/api/presentations/{job.id}/collaborators/{target.id}", headers=_headers(stranger))
        assert resp.status_code == 403


@pytest.mark.integration
class TestListCollaborators:

    def test_any_tenant_member_can_list(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        target = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id, email="collab@example.com")
        viewer = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)
        db_session.add(models.GenerationJobCollaborator(job_id=job.id, user_id=target.id))
        db_session.commit()

        resp = client.get(f"/api/presentations/{job.id}/collaborators", headers=_headers(viewer))
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["email"] == "collab@example.com"

    def test_cross_tenant_viewer_forbidden(self, client, db_session):
        tenant = _make_tenant(db_session, "Home")
        other_tenant = _make_tenant(db_session, "Other")
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        outsider = _make_user(db_session, models.UserRole.CLIENTE.value, other_tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)

        resp = client.get(f"/api/presentations/{job.id}/collaborators", headers=_headers(outsider))
        assert resp.status_code == 403
