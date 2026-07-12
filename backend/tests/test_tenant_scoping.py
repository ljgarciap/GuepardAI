"""
test_tenant_scoping.py — Scoping por tenant en rutas de Brand/Generation
(B7) y Library/Template-Merge (B8).

Spec: docs/specs/autenticacion-multiusuario-multitenant.md
Design: docs/designs/autenticacion-multitenant-design.md §3.3
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


def _make_tenant(db, name="Tenant"):
    tenant = models.Tenant(name=f"{name}_{id(object())}")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def _make_user(db, role, tenant_id=None):
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


def _make_brand(db, tenant_id=None, name=None):
    brand = models.Brand(name=name or f"Brand_{id(object())}", tenant_id=tenant_id)
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


def _headers(user):
    token = security.create_access_token(user.id, user.role, user.tenant_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
class TestBrandDirectoryScoping:

    def test_admin_lists_only_own_tenant_brands(self, client, db_session):
        tenant_a = _make_tenant(db_session, "A")
        tenant_b = _make_tenant(db_session, "B")
        admin_a = _make_user(db_session, models.UserRole.ADMIN.value, tenant_a.id)
        brand_a = _make_brand(db_session, tenant_a.id, "BrandOfA")
        _make_brand(db_session, tenant_b.id, "BrandOfB")

        resp = client.get("/api/brands", headers=_headers(admin_a))

        assert resp.status_code == 200
        names = {b["name"] for b in resp.json()}
        assert "BrandOfA" in names
        assert "BrandOfB" not in names

    def test_superadmin_lists_all_brands(self, client, db_session):
        tenant_a = _make_tenant(db_session, "A2")
        tenant_b = _make_tenant(db_session, "B2")
        superadmin = _make_user(db_session, models.UserRole.SUPERADMIN.value, None)
        _make_brand(db_session, tenant_a.id, "BrandA2")
        _make_brand(db_session, tenant_b.id, "BrandB2")

        resp = client.get("/api/brands", headers=_headers(superadmin))

        names = {b["name"] for b in resp.json()}
        assert "BrandA2" in names and "BrandB2" in names

    def test_admin_created_brand_gets_own_tenant(self, client, db_session):
        tenant = _make_tenant(db_session, "Creator")
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)

        resp = client.post(
            "/api/brands",
            data={"name": f"NewBrand_{id(object())}"},
            headers=_headers(admin),
        )

        assert resp.status_code == 200
        db_session.expire_all()
        brand = db_session.query(models.Brand).filter(models.Brand.name == resp.json()["name"]).first()
        assert brand.tenant_id == tenant.id

    def test_admin_cannot_update_other_tenant_brand(self, client, db_session):
        tenant_a = _make_tenant(db_session, "OwnerA")
        tenant_b = _make_tenant(db_session, "IntruderB")
        intruder = _make_user(db_session, models.UserRole.ADMIN.value, tenant_b.id)
        brand = _make_brand(db_session, tenant_a.id, "ProtectedBrand")

        resp = client.put(
            f"/api/brands/{brand.id}",
            data={"name": "hacked-name"},
            headers=_headers(intruder),
        )

        assert resp.status_code == 403


@pytest.mark.integration
class TestGenerationScoping:

    def test_generate_presentation_rejects_other_tenant_brand(self, client, db_session):
        tenant_a = _make_tenant(db_session, "GenOwner")
        tenant_b = _make_tenant(db_session, "GenIntruder")
        intruder = _make_user(db_session, models.UserRole.ADMIN.value, tenant_b.id)
        brand = _make_brand(db_session, tenant_a.id, "GenBrand")

        resp = client.post(
            "/api/presentations/generate",
            json={
                "style_filename": "x.pptx",
                "knowledge_filename": "x.pdf",
                "prompt": "test",
                "brand_id": brand.id,
            },
            headers=_headers(intruder),
        )

        assert resp.status_code == 403

    def test_job_status_rejects_other_tenant(self, client, db_session):
        tenant_owner = _make_tenant(db_session, "JobOwner")
        tenant_intruder = _make_tenant(db_session, "JobIntruder")
        intruder = _make_user(db_session, models.UserRole.ADMIN.value, tenant_intruder.id)
        brand = _make_brand(db_session, tenant_owner.id, "JobBrand")
        job = models.GenerationJob(
            client_name="pytest", brand_id=brand.id, prompt="x",
            status=models.GenerationJobStatus.COMPLETED,
        )
        db_session.add(job)
        db_session.commit()

        resp = client.get(f"/api/generation/status/{job.id}", headers=_headers(intruder))

        assert resp.status_code == 403

    def test_job_status_allows_same_tenant(self, client, db_session):
        tenant = _make_tenant(db_session, "SameTenant")
        owner = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)
        brand = _make_brand(db_session, tenant.id, "SameTenantBrand")
        job = models.GenerationJob(
            client_name="pytest", brand_id=brand.id, prompt="x",
            status=models.GenerationJobStatus.COMPLETED,
        )
        db_session.add(job)
        db_session.commit()

        resp = client.get(f"/api/generation/status/{job.id}", headers=_headers(owner))

        assert resp.status_code == 200

    def test_job_without_brand_denies_admin_but_allows_superadmin(self, client, db_session):
        """Job legacy/huérfano sin brand_id (pre-alignment): fail-closed para admin/cliente."""
        tenant = _make_tenant(db_session, "OrphanJobTenant")
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)
        superadmin = _make_user(db_session, models.UserRole.SUPERADMIN.value, None)
        job = models.GenerationJob(
            client_name="pytest", brand_id=None, prompt="x",
            status=models.GenerationJobStatus.COMPLETED,
        )
        db_session.add(job)
        db_session.commit()

        assert client.get(f"/api/generation/status/{job.id}", headers=_headers(admin)).status_code == 403
        assert client.get(f"/api/generation/status/{job.id}", headers=_headers(superadmin)).status_code == 200


@pytest.mark.integration
class TestLibraryScoping:

    def test_portfolios_list_scoped_to_tenant(self, client, db_session):
        tenant_a = _make_tenant(db_session, "PortA")
        tenant_b = _make_tenant(db_session, "PortB")
        admin_a = _make_user(db_session, models.UserRole.ADMIN.value, tenant_a.id)
        brand_a = _make_brand(db_session, tenant_a.id, "PortBrandA")
        brand_b = _make_brand(db_session, tenant_b.id, "PortBrandB")
        job_a = models.GenerationJob(client_name="x", brand_id=brand_a.id, prompt="x", status=models.GenerationJobStatus.COMPLETED, pptx_path="a.pptx")
        job_b = models.GenerationJob(client_name="x", brand_id=brand_b.id, prompt="x", status=models.GenerationJobStatus.COMPLETED, pptx_path="b.pptx")
        db_session.add_all([job_a, job_b])
        db_session.commit()

        resp = client.get("/api/library/portfolios", headers=_headers(admin_a))

        assert resp.status_code == 200
        ids = {item["id"] for item in resp.json()["items"]}
        assert job_a.id in ids
        assert job_b.id not in ids

    def test_portfolios_explicit_brand_id_cross_tenant_rejected(self, client, db_session):
        tenant_a = _make_tenant(db_session, "PortC")
        tenant_b = _make_tenant(db_session, "PortD")
        admin_a = _make_user(db_session, models.UserRole.ADMIN.value, tenant_a.id)
        brand_b = _make_brand(db_session, tenant_b.id, "PortBrandD")

        resp = client.get(f"/api/library/portfolios?brand_id={brand_b.id}", headers=_headers(admin_a))

        assert resp.status_code == 403

    def test_available_styles_dash_one_sentinel_no_longer_bypasses_for_admin(self, client, db_session):
        """Regresión: brand_id=-1 (sentinel legacy 'superuser') ya NO debe dar acceso total a un rol no-superadmin."""
        tenant = _make_tenant(db_session, "SentinelTenant")
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)

        resp = client.get("/api/available-styles?brand_id=-1", headers=_headers(admin))

        # -1 ya no es sentinel: se trata como un brand_id común -> 404 (no existe Brand con id -1)
        assert resp.status_code == 404

    def test_template_merge_job_rejects_template_asset_from_other_tenant(self, client, db_session):
        """El template (BrandAsset) puede ser de un brand distinto al del job — igual debe validarse."""
        tenant_owner = _make_tenant(db_session, "TplOwner")
        tenant_intruder = _make_tenant(db_session, "TplIntruder")
        intruder = _make_user(db_session, models.UserRole.ADMIN.value, tenant_intruder.id)
        owner_brand = _make_brand(db_session, tenant_owner.id, "TplOwnerBrand")
        intruder_brand = _make_brand(db_session, tenant_intruder.id, "TplIntruderBrand")

        template_asset = models.BrandAsset(
            brand_id=owner_brand.id,
            file_hash="t" * 64,
            local_path="tpl.pptx",
            category="pptx_template",
        )
        db_session.add(template_asset)
        db_session.commit()

        resp = client.post(
            "/api/template-merge/jobs",
            json={
                "template_asset_id": template_asset.id,
                "knowledge_filename": "k.pdf",
                "prompt": "test",
                "brand_id": intruder_brand.id,
            },
            headers=_headers(intruder),
        )

        assert resp.status_code == 403
