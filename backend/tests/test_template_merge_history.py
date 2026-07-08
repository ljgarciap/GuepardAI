"""
test_template_merge_history.py — Histórico persistente de Template Merge.

Cubre: orden descendente, búsqueda (display_name y filename, escapado de
comodines), rango de fechas, paginación, solo jobs completados, renombrado
(validaciones) y eliminación con limpieza del archivo físico.

Spec: docs/specs/template-merge-job-history.md
Design: docs/designs/template-merge-job-history.md
"""
import datetime
import os
import pytest
from fastapi.testclient import TestClient

import models


@pytest.fixture()
def client(db_session, superadmin_headers):
    from main import app, get_db
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app, headers=superadmin_headers)
    finally:
        app.dependency_overrides.clear()


def _make_template_asset(db, brand_id=None, local_path="templates/test_deck.pptx"):
    asset = models.BrandAsset(
        brand_id=brand_id,
        file_hash=os.urandom(8).hex(),
        local_path=local_path,
        category="pptx_template",
        tags=[],
        manual_tags=[],
        description="Test template asset",
        is_public=0,
    )
    db.add(asset)
    db.flush()
    return asset


def _make_job(db, brand_id, asset_id, *, days_ago=0, display_name=None, filename=None,
              status="completed", output_path=None):
    job = models.TemplateMergeJob(
        brand_id=brand_id,
        template_asset_id=asset_id,
        knowledge_filename="doc.pdf",
        prompt="test",
        status=status,
        display_name=display_name,
        output_path=output_path if output_path is not None else (f"jobs/{filename}" if filename else None),
        created_at=datetime.datetime.utcnow() - datetime.timedelta(days=days_ago),
    )
    db.add(job)
    db.flush()
    return job


# ─────────────────────────────────────────────────────────────────────────────
# LISTADO: orden, búsqueda, fechas, paginación
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration
class TestTemplateMergeHistoryListing:

    def test_ordered_newest_first(self, client, db_session, sample_brand):
        asset = _make_template_asset(db_session, brand_id=sample_brand.id)
        _make_job(db_session, sample_brand.id, asset.id, days_ago=5, filename="old.pptx")
        _make_job(db_session, sample_brand.id, asset.id, days_ago=0, filename="newest.pptx")
        _make_job(db_session, sample_brand.id, asset.id, days_ago=2, filename="middle.pptx")

        res = client.get("/api/template-merge/jobs")
        assert res.status_code == 200
        body = res.json()
        names = [i["filename"] for i in body["items"]]
        assert names == ["newest.pptx", "middle.pptx", "old.pptx"]
        assert body["total"] == 3
        assert body["page"] == 1

    def test_search_matches_display_name_and_filename(self, client, db_session, sample_brand):
        asset = _make_template_asset(db_session, brand_id=sample_brand.id)
        _make_job(db_session, sample_brand.id, asset.id, display_name="Tesco Clubcard Pitch", filename="Merge_1.pptx")
        _make_job(db_session, sample_brand.id, asset.id, filename="tesco_keynote.pptx")
        _make_job(db_session, sample_brand.id, asset.id, filename="other_brand.pptx")

        res = client.get("/api/template-merge/jobs", params={"search": "tesco"})
        body = res.json()
        assert body["total"] == 2
        display_names = {i["display_name"] for i in body["items"]}
        assert display_names == {"Tesco Clubcard Pitch", "tesco_keynote.pptx"}

    def test_search_escapes_like_wildcards(self, client, db_session, sample_brand):
        asset = _make_template_asset(db_session, brand_id=sample_brand.id)
        _make_job(db_session, sample_brand.id, asset.id, display_name="100% Loyalty", filename="a.pptx")
        _make_job(db_session, sample_brand.id, asset.id, display_name="Loyalty Deck", filename="b.pptx")

        res = client.get("/api/template-merge/jobs", params={"search": "100%"})
        body = res.json()
        assert body["total"] == 1
        assert body["items"][0]["display_name"] == "100% Loyalty"

    def test_date_range_inclusive(self, client, db_session, sample_brand):
        asset = _make_template_asset(db_session, brand_id=sample_brand.id)
        _make_job(db_session, sample_brand.id, asset.id, days_ago=10, filename="too_old.pptx")
        target = _make_job(db_session, sample_brand.id, asset.id, days_ago=3, filename="in_range.pptx")
        _make_job(db_session, sample_brand.id, asset.id, days_ago=0, filename="too_new.pptx")

        today_utc = datetime.datetime.utcnow().date()
        d_from = (today_utc - datetime.timedelta(days=4)).isoformat()
        d_to = (today_utc - datetime.timedelta(days=3)).isoformat()
        res = client.get("/api/template-merge/jobs", params={"date_from": d_from, "date_to": d_to})
        body = res.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == target.id

    def test_inverted_date_range_returns_422(self, client):
        res = client.get("/api/template-merge/jobs", params={
            "date_from": "2026-06-11", "date_to": "2026-06-01"
        })
        assert res.status_code == 422

    def test_pagination_and_out_of_range_page(self, client, db_session, sample_brand):
        asset = _make_template_asset(db_session, brand_id=sample_brand.id)
        for i in range(5):
            _make_job(db_session, sample_brand.id, asset.id, days_ago=i, filename=f"deck_{i}.pptx")

        res = client.get("/api/template-merge/jobs", params={"page": 2, "page_size": 2})
        body = res.json()
        assert body["total"] == 5
        assert len(body["items"]) == 2
        assert body["items"][0]["filename"] == "deck_2.pptx"

        res = client.get("/api/template-merge/jobs", params={"page": 99, "page_size": 2})
        body = res.json()
        assert res.status_code == 200
        assert body["items"] == []
        assert body["total"] == 5

    def test_only_completed_jobs_listed(self, client, db_session, sample_brand):
        asset = _make_template_asset(db_session, brand_id=sample_brand.id)
        _make_job(db_session, sample_brand.id, asset.id, filename="done.pptx")
        _make_job(db_session, sample_brand.id, asset.id, filename="wip.pptx", status="processing")
        _make_job(db_session, sample_brand.id, asset.id, filename="failed.pptx", status="error")

        body = client.get("/api/template-merge/jobs").json()
        assert body["total"] == 1
        assert body["items"][0]["filename"] == "done.pptx"


# ─────────────────────────────────────────────────────────────────────────────
# RENOMBRADO
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration
class TestTemplateMergeHistoryRename:

    def test_rename_persists_and_search_finds_new_name(self, client, db_session, sample_brand):
        asset = _make_template_asset(db_session, brand_id=sample_brand.id)
        job = _make_job(db_session, sample_brand.id, asset.id, filename="Merge_X.pptx")

        res = client.patch(f"/api/template-merge/jobs/{job.id}", json={"display_name": "  Pitch Q3 Tesco  "})
        assert res.status_code == 200
        assert res.json()["display_name"] == "Pitch Q3 Tesco"

        body = client.get("/api/template-merge/jobs", params={"search": "Pitch Q3"}).json()
        assert body["total"] == 1
        assert body["items"][0]["display_name"] == "Pitch Q3 Tesco"

    def test_rename_validations(self, client, db_session, sample_brand):
        asset = _make_template_asset(db_session, brand_id=sample_brand.id)
        job = _make_job(db_session, sample_brand.id, asset.id, filename="a.pptx")

        assert client.patch(f"/api/template-merge/jobs/{job.id}", json={"display_name": "   "}).status_code == 422
        assert client.patch(f"/api/template-merge/jobs/{job.id}", json={"display_name": "x" * 121}).status_code == 422
        assert client.patch("/api/template-merge/jobs/999999", json={"display_name": "valid"}).status_code == 404

    def test_rename_does_not_touch_output_path(self, client, db_session, sample_brand):
        asset = _make_template_asset(db_session, brand_id=sample_brand.id)
        job = _make_job(db_session, sample_brand.id, asset.id, filename="physical_name.pptx")
        original_path = job.output_path

        client.patch(f"/api/template-merge/jobs/{job.id}", json={"display_name": "New Label"})

        db_session.refresh(job)
        assert job.output_path == original_path
        assert job.display_name == "New Label"


# ─────────────────────────────────────────────────────────────────────────────
# ELIMINACIÓN
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration
class TestTemplateMergeHistoryDelete:

    def test_delete_removes_job_and_physical_file(self, client, db_session, sample_brand, tmp_path):
        pptx_file = tmp_path / "to_delete.pptx"
        pptx_file.write_bytes(b"fake pptx")
        asset = _make_template_asset(db_session, brand_id=sample_brand.id)
        job = _make_job(db_session, sample_brand.id, asset.id, output_path=str(pptx_file))
        job_id = job.id

        res = client.delete(f"/api/template-merge/jobs/{job_id}")
        assert res.status_code == 200
        assert res.json() == {"deleted": True, "id": job_id}

        assert db_session.query(models.TemplateMergeJob).get(job_id) is None
        assert not os.path.exists(str(pptx_file))

    def test_delete_tolerates_missing_file(self, client, db_session, sample_brand):
        asset = _make_template_asset(db_session, brand_id=sample_brand.id)
        job = _make_job(db_session, sample_brand.id, asset.id, output_path="jobs/ghost_file.pptx")

        res = client.delete(f"/api/template-merge/jobs/{job.id}")
        assert res.status_code == 200
        assert res.json()["deleted"] is True

    def test_delete_blocked_while_pipeline_active(self, client, db_session, sample_brand):
        asset = _make_template_asset(db_session, brand_id=sample_brand.id)
        job = _make_job(db_session, sample_brand.id, asset.id, filename="wip.pptx", status="processing")

        res = client.delete(f"/api/template-merge/jobs/{job.id}")
        assert res.status_code == 409
        assert db_session.query(models.TemplateMergeJob).get(job.id) is not None

    def test_delete_error_status_allowed(self, client, db_session, sample_brand):
        asset = _make_template_asset(db_session, brand_id=sample_brand.id)
        job = _make_job(db_session, sample_brand.id, asset.id, filename="failed.pptx", status="error")

        assert client.delete(f"/api/template-merge/jobs/{job.id}").status_code == 200

    def test_delete_twice_returns_404(self, client, db_session, sample_brand):
        asset = _make_template_asset(db_session, brand_id=sample_brand.id)
        job = _make_job(db_session, sample_brand.id, asset.id, filename="once.pptx")
        job_id = job.id

        assert client.delete(f"/api/template-merge/jobs/{job_id}").status_code == 200
        assert client.delete(f"/api/template-merge/jobs/{job_id}").status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# TENANT SCOPING (mismo patrón que test_tenant_scoping.py::TestLibraryScoping)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration
class TestTemplateMergeHistoryTenantScoping:

    def _make_tenant(self, db, name="Tenant"):
        tenant = models.Tenant(name=f"{name}_{id(object())}")
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
        return tenant

    def _make_user(self, db, role, tenant_id=None):
        from auth import security
        user = models.User(
            email=f"{role}_{id(object())}@example.com",
            hashed_password=security.hash_password("irrelevant-password"),
            role=role,
            tenant_id=tenant_id,
            is_active=1,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def _make_brand(self, db, tenant_id=None, name=None):
        brand = models.Brand(name=name or f"Brand_{id(object())}", tenant_id=tenant_id)
        db.add(brand)
        db.commit()
        db.refresh(brand)
        return brand

    def _headers(self, user):
        from auth import security
        token = security.create_access_token(user.id, user.role, user.tenant_id)
        return {"Authorization": f"Bearer {token}"}

    @pytest.fixture()
    def scoping_client(self, db_session):
        from main import app, get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            yield TestClient(app)
        finally:
            app.dependency_overrides.clear()

    def test_list_scoped_to_tenant(self, scoping_client, db_session):
        tenant_a = self._make_tenant(db_session, "TmA")
        tenant_b = self._make_tenant(db_session, "TmB")
        admin_a = self._make_user(db_session, models.UserRole.ADMIN.value, tenant_a.id)
        brand_a = self._make_brand(db_session, tenant_a.id, "TmBrandA")
        brand_b = self._make_brand(db_session, tenant_b.id, "TmBrandB")
        asset_a = _make_template_asset(db_session, brand_id=brand_a.id)
        asset_b = _make_template_asset(db_session, brand_id=brand_b.id)
        job_a = _make_job(db_session, brand_a.id, asset_a.id, filename="a.pptx")
        job_b = _make_job(db_session, brand_b.id, asset_b.id, filename="b.pptx")
        db_session.commit()

        resp = scoping_client.get("/api/template-merge/jobs", headers=self._headers(admin_a))

        assert resp.status_code == 200
        ids = {item["id"] for item in resp.json()["items"]}
        assert job_a.id in ids
        assert job_b.id not in ids

    def test_explicit_brand_id_cross_tenant_rejected(self, scoping_client, db_session):
        tenant_a = self._make_tenant(db_session, "TmC")
        tenant_b = self._make_tenant(db_session, "TmD")
        admin_a = self._make_user(db_session, models.UserRole.ADMIN.value, tenant_a.id)
        brand_b = self._make_brand(db_session, tenant_b.id, "TmBrandD")

        resp = scoping_client.get(f"/api/template-merge/jobs?brand_id={brand_b.id}", headers=self._headers(admin_a))

        assert resp.status_code == 403

    def test_rename_rejects_other_tenant(self, scoping_client, db_session):
        tenant_owner = self._make_tenant(db_session, "TmOwner")
        tenant_intruder = self._make_tenant(db_session, "TmIntruder")
        intruder = self._make_user(db_session, models.UserRole.ADMIN.value, tenant_intruder.id)
        brand = self._make_brand(db_session, tenant_owner.id, "TmOwnerBrand")
        asset = _make_template_asset(db_session, brand_id=brand.id)
        job = _make_job(db_session, brand.id, asset.id, filename="protected.pptx")
        db_session.commit()

        resp = scoping_client.patch(
            f"/api/template-merge/jobs/{job.id}",
            json={"display_name": "hacked"},
            headers=self._headers(intruder),
        )

        assert resp.status_code == 403
