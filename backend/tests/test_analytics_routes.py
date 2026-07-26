"""
test_analytics_routes.py — /api/presentations/{job_id}/activity,
/api/admin/analytics/usage, /api/admin/usage-reports
(reviews-analitica-colaboracion, ítems 5 y 7).

Spec: docs/specs/reviews-analitica-colaboracion.md
"""
import datetime
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
    from services.core.auth_service import get_current_tos_version
    user = models.User(
        email=email or f"{role}_{uuid.uuid4().hex}@example.com",
        hashed_password=security.hash_password("irrelevant-password"),
        role=role,
        tenant_id=tenant_id,
        is_active=1,
        # Estas rutas no prueban el gate de ToS (auth/dependencies.py) — se
        # asume aceptado para no acoplar tests de analytics a esa feature.
        tos_accepted=1,
        tos_accepted_version=get_current_tos_version(),
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
class TestRecordActivityEvent:

    def test_records_session_time(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)

        resp = client.post(f"/api/presentations/{job.id}/activity", json={"event_type": "session_time_seconds", "value": 120}, headers=_headers(owner))
        assert resp.status_code == 200

        row = db_session.query(models.UserActivityEvent).filter(models.UserActivityEvent.job_id == job.id).first()
        assert row.event_type == "session_time_seconds"
        assert row.value == 120

    def test_rejects_slide_edit_event_type(self, client, db_session):
        """slide_edit se registra server-side (PUT slides), no es postable por el cliente."""
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)

        resp = client.post(f"/api/presentations/{job.id}/activity", json={"event_type": "slide_edit", "value": 1}, headers=_headers(owner))
        assert resp.status_code == 422

    def test_rejects_non_positive_value(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)

        resp = client.post(f"/api/presentations/{job.id}/activity", json={"event_type": "session_time_seconds", "value": 0}, headers=_headers(owner))
        assert resp.status_code == 422

    def test_cross_tenant_forbidden(self, client, db_session):
        tenant = _make_tenant(db_session, "Home")
        other_tenant = _make_tenant(db_session, "Other")
        brand = _make_brand(db_session, tenant.id)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        outsider = _make_user(db_session, models.UserRole.CLIENTE.value, other_tenant.id)
        job = _make_job(db_session, brand.id, owner_id=owner.id)

        resp = client.post(f"/api/presentations/{job.id}/activity", json={"event_type": "session_time_seconds", "value": 5}, headers=_headers(outsider))
        assert resp.status_code == 403


@pytest.mark.integration
class TestUsageAnalytics:

    def test_aggregates_presentations_edits_time_rating(self, client, db_session):
        tenant = _make_tenant(db_session)
        brand = _make_brand(db_session, tenant.id)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)
        member = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id, email="member@example.com")
        job1 = _make_job(db_session, brand.id, owner_id=member.id)
        job2 = _make_job(db_session, brand.id, owner_id=member.id)

        db_session.add_all([
            models.UserActivityEvent(job_id=job1.id, user_id=member.id, event_type="slide_edit", value=3),
            models.UserActivityEvent(job_id=job1.id, user_id=member.id, event_type="slide_edit", value=2),
            models.UserActivityEvent(job_id=job1.id, user_id=member.id, event_type="session_time_seconds", value=100),
            # visible + flagged deben contar en el promedio, hidden no (regresión Senior Review)
            models.PresentationReview(job_id=job1.id, user_id=admin.id, rating=4, moderation_status="visible"),
            models.PresentationReview(job_id=job2.id, user_id=admin.id, rating=2, moderation_status="flagged"),
        ])
        db_session.commit()

        resp = client.get("/api/admin/analytics/usage", headers=_headers(admin))
        assert resp.status_code == 200
        rows = {r["user_id"]: r for r in resp.json()["users"]}
        row = rows[member.id]
        assert row["presentations_created"] == 2
        assert row["edits"] == 5
        assert row["time_spent_seconds"] == 100
        assert row["rating_average_received"] == 3.0  # avg(4, 2), no solo 4

    def test_department_name_resolved(self, client, db_session):
        tenant = _make_tenant(db_session)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)
        dept = models.Department(tenant_id=tenant.id, name="Engineering")
        db_session.add(dept)
        db_session.commit()
        db_session.refresh(dept)
        member = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        member.department_id = dept.id
        db_session.commit()

        resp = client.get("/api/admin/analytics/usage", headers=_headers(admin))
        rows = {r["user_id"]: r for r in resp.json()["users"]}
        assert rows[member.id]["department_name"] == "Engineering"

    def test_admin_scoped_to_own_tenant(self, client, db_session):
        tenant_a = _make_tenant(db_session, "A")
        tenant_b = _make_tenant(db_session, "B")
        admin_a = _make_user(db_session, models.UserRole.ADMIN.value, tenant_a.id)
        _make_user(db_session, models.UserRole.CLIENTE.value, tenant_a.id, email="a.member@example.com")
        _make_user(db_session, models.UserRole.CLIENTE.value, tenant_b.id, email="b.member@example.com")

        resp = client.get("/api/admin/analytics/usage", headers=_headers(admin_a))
        emails = {r["email"] for r in resp.json()["users"]}
        assert "a.member@example.com" in emails
        assert "b.member@example.com" not in emails

    def test_cliente_forbidden(self, client, db_session):
        tenant = _make_tenant(db_session)
        cliente = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)

        resp = client.get("/api/admin/analytics/usage", headers=_headers(cliente))
        assert resp.status_code == 403

    def test_no_users_returns_empty_list_without_error(self, client, db_session, superadmin_headers):
        resp = client.get("/api/admin/analytics/usage?tenant_id=999999", headers=superadmin_headers)
        assert resp.status_code == 200
        assert resp.json() == {"users": []}


@pytest.mark.integration
class TestUsageReports:

    def test_admin_sees_only_own_tenant_reports(self, client, db_session):
        tenant_a = _make_tenant(db_session, "A2")
        tenant_b = _make_tenant(db_session, "B2")
        admin_a = _make_user(db_session, models.UserRole.ADMIN.value, tenant_a.id)
        now = datetime.datetime.utcnow()
        db_session.add_all([
            models.UsageReport(tenant_id=tenant_a.id, period_start=now, period_end=now, payload_json={"presentations_created": 1}),
            models.UsageReport(tenant_id=tenant_b.id, period_start=now, period_end=now, payload_json={"presentations_created": 2}),
            models.UsageReport(tenant_id=None, period_start=now, period_end=now, payload_json={"presentations_created": 3}),
        ])
        db_session.commit()

        resp = client.get("/api/admin/usage-reports", headers=_headers(admin_a))
        tenant_ids = {r["tenant_id"] for r in resp.json()}
        assert tenant_ids == {tenant_a.id}

    def test_superadmin_sees_all_including_global(self, client, db_session, superadmin_headers):
        now = datetime.datetime.utcnow()
        tenant = _make_tenant(db_session, "A3")
        db_session.add_all([
            models.UsageReport(tenant_id=tenant.id, period_start=now, period_end=now, payload_json={}),
            models.UsageReport(tenant_id=None, period_start=now, period_end=now, payload_json={}),
        ])
        db_session.commit()

        resp = client.get("/api/admin/usage-reports", headers=superadmin_headers)
        tenant_ids = {r["tenant_id"] for r in resp.json()}
        assert tenant.id in tenant_ids
        assert None in tenant_ids
