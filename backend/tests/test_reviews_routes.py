"""
test_reviews_routes.py — /api/presentations/{job_id}/reviews + /api/admin/reviews
+ moderation blocklist (reviews-analitica-colaboracion).

Cubre especialmente el bug de Senior Review arreglado en 7ee3a13: una review
'flagged' (auto-tag del filtro de palabras) NO debe desaparecer del listado
para usuarios no-admin ni excluirse del rating_average — solo 'hidden'
(acción explícita de un admin) debe hacerlo.

Spec: docs/specs/reviews-analitica-colaboracion.md
"""
import datetime
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


def _make_job(db, brand_id, owner_id=None, created_at=None):
    job = models.GenerationJob(
        brand_id=brand_id,
        owner_id=owner_id,
        prompt="test prompt",
        status=models.GenerationJobStatus.COMPLETED,
        created_at=created_at or datetime.datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _headers(user):
    token = security.create_access_token(user.id, user.role, user.tenant_id)
    return {"Authorization": f"Bearer {token}"}


def _set_blocklist(db, terms):
    cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == "review_moderation_blocklist_v1").first()
    value = json.dumps(terms)
    if cfg is None:
        db.add(models.SystemConfig(key="review_moderation_blocklist_v1", value=value))
    else:
        cfg.value = value
    db.commit()


@pytest.mark.integration
class TestUpsertReview:

    def test_rating_out_of_range_rejected(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)

        resp = client.post(f"/api/presentations/{job.id}/reviews", json={"rating": 6}, headers=_headers(owner))
        assert resp.status_code == 422

    def test_owner_can_create_review(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)

        resp = client.post(f"/api/presentations/{job.id}/reviews", json={"rating": 5, "comment": "great"}, headers=_headers(owner))
        assert resp.status_code == 200
        assert resp.json()["rating"] == 5
        assert resp.json()["moderation_status"] == "visible"

    def test_collaborator_can_create_review(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        collaborator = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)
        db_session.add(models.GenerationJobCollaborator(job_id=job.id, user_id=collaborator.id))
        db_session.commit()

        resp = client.post(f"/api/presentations/{job.id}/reviews", json={"rating": 4}, headers=_headers(collaborator))
        assert resp.status_code == 200

    def test_non_owner_non_collaborator_forbidden(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        stranger = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)

        resp = client.post(f"/api/presentations/{job.id}/reviews", json={"rating": 3}, headers=_headers(stranger))
        assert resp.status_code == 403

    def test_upsert_updates_existing_review_in_place(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)

        client.post(f"/api/presentations/{job.id}/reviews", json={"rating": 2, "comment": "meh"}, headers=_headers(owner))
        resp = client.post(f"/api/presentations/{job.id}/reviews", json={"rating": 5, "comment": "actually great"}, headers=_headers(owner))

        assert resp.status_code == 200
        assert resp.json()["rating"] == 5
        count = db_session.query(models.PresentationReview).filter(models.PresentationReview.job_id == job.id).count()
        assert count == 1

    def test_window_closed_after_six_months_rejected(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        old_job = _make_job(db_session, brand.id, owner_id=owner.id, created_at=datetime.datetime.utcnow() - datetime.timedelta(days=200))

        resp = client.post(f"/api/presentations/{old_job.id}/reviews", json={"rating": 4}, headers=_headers(owner))
        assert resp.status_code == 409

    def test_comment_with_blocklisted_word_gets_flagged(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)
        _set_blocklist(db_session, ["badword"])

        resp = client.post(f"/api/presentations/{job.id}/reviews", json={"rating": 3, "comment": "this has a BadWord in it"}, headers=_headers(owner))
        assert resp.status_code == 200
        assert resp.json()["moderation_status"] == "flagged"


@pytest.mark.integration
class TestDeleteOwnReview:

    def test_delete_own_review_soft_deletes(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)
        client.post(f"/api/presentations/{job.id}/reviews", json={"rating": 3}, headers=_headers(owner))

        resp = client.delete(f"/api/presentations/{job.id}/reviews/me", headers=_headers(owner))
        assert resp.status_code == 200

        review = db_session.query(models.PresentationReview).filter(models.PresentationReview.job_id == job.id).first()
        assert review.is_deleted is True

    def test_delete_nonexistent_review_404(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)

        resp = client.delete(f"/api/presentations/{job.id}/reviews/me", headers=_headers(owner))
        assert resp.status_code == 404


@pytest.mark.integration
class TestListReviews:

    def test_non_admin_sees_flagged_not_hidden(self, client, db_session):
        """Regresión del bug de Senior Review: antes, el filtro == 'visible' ocultaba
        también las reviews 'flagged' (no solo 'hidden') a usuarios no-admin."""
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        reviewer_flagged = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        reviewer_hidden = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)

        flagged = models.PresentationReview(job_id=job.id, user_id=reviewer_flagged.id, rating=3, moderation_status="flagged")
        hidden = models.PresentationReview(job_id=job.id, user_id=reviewer_hidden.id, rating=1, moderation_status="hidden")
        visible = models.PresentationReview(job_id=job.id, user_id=owner.id, rating=5, moderation_status="visible")
        db_session.add_all([flagged, hidden, visible])
        db_session.commit()

        resp = client.get(f"/api/presentations/{job.id}/reviews", headers=_headers(owner))
        assert resp.status_code == 200
        body = resp.json()
        statuses = {r["moderation_status"] for r in body["reviews"]}
        assert "flagged" in statuses
        assert "hidden" not in statuses
        assert len(body["reviews"]) == 2

    def test_rating_average_includes_flagged_excludes_hidden(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        r1 = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        r2 = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)

        # visible=4, flagged=2 -> deben contar ambas: avg = 3.0, count = 2
        # hidden=1 -> NO debe contar
        db_session.add_all([
            models.PresentationReview(job_id=job.id, user_id=owner.id, rating=4, moderation_status="visible"),
            models.PresentationReview(job_id=job.id, user_id=r1.id, rating=2, moderation_status="flagged"),
            models.PresentationReview(job_id=job.id, user_id=r2.id, rating=1, moderation_status="hidden"),
        ])
        db_session.commit()

        resp = client.get(f"/api/presentations/{job.id}/reviews", headers=_headers(owner))
        body = resp.json()
        assert body["rating_average"] == 3.0
        assert body["rating_count"] == 2

    def test_admin_sees_hidden_reviews_too(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)
        db_session.add(models.PresentationReview(job_id=job.id, user_id=owner.id, rating=1, moderation_status="hidden"))
        db_session.commit()

        resp = client.get(f"/api/presentations/{job.id}/reviews", headers=_headers(admin))
        assert resp.status_code == 200
        assert len(resp.json()["reviews"]) == 1

    def test_soft_deleted_review_excluded(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)
        db_session.add(models.PresentationReview(job_id=job.id, user_id=owner.id, rating=5, moderation_status="visible", is_deleted=True))
        db_session.commit()

        resp = client.get(f"/api/presentations/{job.id}/reviews", headers=_headers(owner))
        assert resp.json()["reviews"] == []
        assert resp.json()["rating_count"] == 0


@pytest.mark.integration
class TestListAdminReviews:

    def test_status_filter_flagged_only(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)
        db_session.add_all([
            models.PresentationReview(job_id=job.id, user_id=owner.id, rating=3, moderation_status="flagged"),
        ])
        db_session.commit()
        other_reviewer = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        db_session.add(models.PresentationReview(job_id=job.id, user_id=other_reviewer.id, rating=5, moderation_status="visible"))
        db_session.commit()

        resp = client.get("/api/admin/reviews?status_filter=flagged", headers=_headers(admin))
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["moderation_status"] == "flagged"
        assert "job_display_name" in body[0]

    def test_admin_scoped_to_own_tenant(self, client, db_session):
        tenant_a = _make_tenant(db_session, "TenantA")
        tenant_b = _make_tenant(db_session, "TenantB")
        brand_a = _make_brand(db_session, tenant_a.id)
        brand_b = _make_brand(db_session, tenant_b.id)
        admin_a = _make_user(db_session, models.UserRole.ADMIN.value, tenant_a.id)
        owner_a = _make_user(db_session, models.UserRole.CLIENTE.value, tenant_a.id)
        owner_b = _make_user(db_session, models.UserRole.CLIENTE.value, tenant_b.id)
        job_a = _make_job(db_session, brand_a.id, owner_id=owner_a.id)
        job_b = _make_job(db_session, brand_b.id, owner_id=owner_b.id)
        db_session.add_all([
            models.PresentationReview(job_id=job_a.id, user_id=owner_a.id, rating=3, moderation_status="flagged"),
            models.PresentationReview(job_id=job_b.id, user_id=owner_b.id, rating=3, moderation_status="flagged"),
        ])
        db_session.commit()

        resp = client.get("/api/admin/reviews", headers=_headers(admin_a))
        job_ids = {r["job_id"] for r in resp.json()}
        assert job_ids == {job_a.id}

    def test_invalid_status_filter_rejected(self, client, db_session):
        tenant = _make_tenant(db_session)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)

        resp = client.get("/api/admin/reviews?status_filter=bogus", headers=_headers(admin))
        assert resp.status_code == 422

    def test_cliente_forbidden(self, client, db_session):
        tenant = _make_tenant(db_session)
        cliente = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)

        resp = client.get("/api/admin/reviews", headers=_headers(cliente))
        assert resp.status_code == 403


@pytest.mark.integration
class TestUpdateReviewModeration:

    def test_admin_hides_review(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)
        review = models.PresentationReview(job_id=job.id, user_id=owner.id, rating=1, moderation_status="flagged")
        db_session.add(review)
        db_session.commit()
        db_session.refresh(review)

        resp = client.patch(f"/api/admin/reviews/{review.id}/moderation", json={"status": "hidden"}, headers=_headers(admin))
        assert resp.status_code == 200
        assert resp.json()["moderation_status"] == "hidden"

    def test_cannot_set_status_to_flagged_manually(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)
        review = models.PresentationReview(job_id=job.id, user_id=owner.id, rating=1, moderation_status="visible")
        db_session.add(review)
        db_session.commit()
        db_session.refresh(review)

        resp = client.patch(f"/api/admin/reviews/{review.id}/moderation", json={"status": "flagged"}, headers=_headers(admin))
        assert resp.status_code == 422

    def test_cross_tenant_admin_forbidden(self, client, db_session):
        tenant_a = _make_tenant(db_session, "TA")
        tenant_b = _make_tenant(db_session, "TB")
        brand_b = _make_brand(db_session, tenant_b.id)
        admin_a = _make_user(db_session, models.UserRole.ADMIN.value, tenant_a.id)
        owner_b = _make_user(db_session, models.UserRole.CLIENTE.value, tenant_b.id)
        job_b = _make_job(db_session, brand_b.id, owner_id=owner_b.id)
        review = models.PresentationReview(job_id=job_b.id, user_id=owner_b.id, rating=1, moderation_status="flagged")
        db_session.add(review)
        db_session.commit()
        db_session.refresh(review)

        resp = client.patch(f"/api/admin/reviews/{review.id}/moderation", json={"status": "hidden"}, headers=_headers(admin_a))
        assert resp.status_code == 403


@pytest.mark.integration
class TestModerationBlocklist:

    def test_admin_cannot_read_blocklist(self, client, db_session):
        tenant = _make_tenant(db_session)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)

        resp = client.get("/api/admin/config/review-moderation-blocklist", headers=_headers(admin))
        assert resp.status_code == 403

    def test_superadmin_reads_and_updates_blocklist(self, client, db_session, superadmin_headers):
        resp = client.patch("/api/admin/config/review-moderation-blocklist", json={"terms": ["spam", "scam"]}, headers=superadmin_headers)
        assert resp.status_code == 200
        assert resp.json()["terms"] == ["spam", "scam"]

        resp = client.get("/api/admin/config/review-moderation-blocklist", headers=superadmin_headers)
        assert resp.status_code == 200
        assert resp.json()["terms"] == ["spam", "scam"]
