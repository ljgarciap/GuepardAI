"""
test_prompt_favorites.py — /api/prompts/favorites (biblioteca-prompts-favoritos).

Cubre: CRUD básico, validación, y la visibilidad de 3 niveles (cliente ve los
propios, admin ve los de su tenant, superadmin ve todos) con escritura
exclusiva del dueño en todos los roles — el caso crítico que el Senior
Reviewer marcó como riesgo en el design doc.

Spec: docs/specs/biblioteca-prompts-favoritos.md
Design: docs/designs/biblioteca-prompts-favoritos.md
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
    from services.core.auth_service import get_current_tos_version
    user = models.User(
        email=email or f"{role}_{uuid.uuid4().hex}@example.com",
        hashed_password=security.hash_password("irrelevant-password"),
        role=role,
        tenant_id=tenant_id,
        is_active=1,
        # Estas rutas no prueban el gate de ToS (auth/dependencies.py) — se
        # asume aceptado para no acoplar tests de favorites a esa feature.
        tos_accepted=1,
        tos_accepted_version=get_current_tos_version(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_favorite(db, user_id, tenant_id, title="Fav", prompt_text="Some prompt", source_job_id=None):
    fav = models.PromptFavorite(
        user_id=user_id, tenant_id=tenant_id, title=title, prompt_text=prompt_text,
        source_job_id=source_job_id,
    )
    db.add(fav)
    db.commit()
    db.refresh(fav)
    return fav


def _headers(user):
    token = security.create_access_token(user.id, user.role, user.tenant_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
class TestCreateFavorite:

    def test_create_assigns_owner_and_tenant_from_current_user(self, client, db_session):
        tenant = _make_tenant(db_session)
        user = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)

        resp = client.post(
            "/api/prompts/favorites",
            json={"title": "My favorite", "prompt_text": "Do a thing"},
            headers=_headers(user),
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == "My favorite"
        assert body["owner_email"] == user.email
        fav = db_session.query(models.PromptFavorite).get(body["id"])
        assert fav.user_id == user.id
        assert fav.tenant_id == tenant.id

    def test_create_ignores_user_id_and_tenant_id_in_body(self, client, db_session):
        """user_id/tenant_id nunca vienen del body — siempre del current_user."""
        tenant = _make_tenant(db_session)
        other_tenant = _make_tenant(db_session)
        user = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)

        resp = client.post(
            "/api/prompts/favorites",
            json={"title": "T", "prompt_text": "P", "user_id": 999999, "tenant_id": other_tenant.id},
            headers=_headers(user),
        )

        assert resp.status_code == 201
        fav = db_session.query(models.PromptFavorite).get(resp.json()["id"])
        assert fav.user_id == user.id
        assert fav.tenant_id == tenant.id

    def test_create_rejects_empty_title(self, client, db_session):
        tenant = _make_tenant(db_session)
        user = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)

        resp = client.post(
            "/api/prompts/favorites",
            json={"title": "", "prompt_text": "P"},
            headers=_headers(user),
        )

        assert resp.status_code == 422

    def test_create_rejects_empty_prompt_text(self, client, db_session):
        tenant = _make_tenant(db_session)
        user = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)

        resp = client.post(
            "/api/prompts/favorites",
            json={"title": "T", "prompt_text": ""},
            headers=_headers(user),
        )

        assert resp.status_code == 422

    def test_create_persists_prompt_metadata(self, client, db_session):
        tenant = _make_tenant(db_session)
        user = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        metadata = {"objective": "sell", "tone": "urgent", "no_buzzwords": True}

        resp = client.post(
            "/api/prompts/favorites",
            json={"title": "T", "prompt_text": "P", "prompt_metadata": metadata},
            headers=_headers(user),
        )

        assert resp.status_code == 201
        assert resp.json()["prompt_metadata"] == metadata


@pytest.mark.integration
class TestListFavoritesVisibility:

    def test_cliente_sees_only_own_favorites(self, client, db_session):
        tenant = _make_tenant(db_session)
        me = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        teammate = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        mine = _make_favorite(db_session, me.id, tenant.id, title="Mine")
        _make_favorite(db_session, teammate.id, tenant.id, title="Teammate's")

        resp = client.get("/api/prompts/favorites", headers=_headers(me))

        assert resp.status_code == 200
        ids = {item["id"] for item in resp.json()}
        assert ids == {mine.id}

    def test_admin_sees_own_and_team_favorites_but_not_other_tenants(self, client, db_session):
        tenant_a = _make_tenant(db_session)
        tenant_b = _make_tenant(db_session)
        admin_a = _make_user(db_session, models.UserRole.ADMIN.value, tenant_a.id)
        cliente_a = _make_user(db_session, models.UserRole.CLIENTE.value, tenant_a.id)
        cliente_b = _make_user(db_session, models.UserRole.CLIENTE.value, tenant_b.id)
        own = _make_favorite(db_session, admin_a.id, tenant_a.id, title="AdminOwn")
        teammate = _make_favorite(db_session, cliente_a.id, tenant_a.id, title="TeamOfA")
        _make_favorite(db_session, cliente_b.id, tenant_b.id, title="OtherTenant")

        resp = client.get("/api/prompts/favorites", headers=_headers(admin_a))

        assert resp.status_code == 200
        ids = {item["id"] for item in resp.json()}
        assert ids == {own.id, teammate.id}

    def test_superadmin_sees_all_tenants(self, client, db_session):
        tenant_a = _make_tenant(db_session)
        tenant_b = _make_tenant(db_session)
        superadmin = _make_user(db_session, models.UserRole.SUPERADMIN.value, None)
        cliente_a = _make_user(db_session, models.UserRole.CLIENTE.value, tenant_a.id)
        cliente_b = _make_user(db_session, models.UserRole.CLIENTE.value, tenant_b.id)
        fav_a = _make_favorite(db_session, cliente_a.id, tenant_a.id, title="A")
        fav_b = _make_favorite(db_session, cliente_b.id, tenant_b.id, title="B")

        resp = client.get("/api/prompts/favorites", headers=_headers(superadmin))

        assert resp.status_code == 200
        ids = {item["id"] for item in resp.json()}
        assert {fav_a.id, fav_b.id}.issubset(ids)


@pytest.mark.integration
class TestWriteAuthorizationIsOwnerOnly:
    """El caso crítico marcado en el design doc: visibilidad extendida de
    admin/superadmin es de solo lectura — escritura siempre exclusiva del
    dueño, sin excepción de rol."""

    def test_owner_can_update_own_favorite(self, client, db_session):
        tenant = _make_tenant(db_session)
        user = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        fav = _make_favorite(db_session, user.id, tenant.id, title="Old")

        resp = client.put(
            f"/api/prompts/favorites/{fav.id}",
            json={"title": "New"},
            headers=_headers(user),
        )

        assert resp.status_code == 200
        assert resp.json()["title"] == "New"

    def test_owner_can_delete_own_favorite(self, client, db_session):
        tenant = _make_tenant(db_session)
        user = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        fav = _make_favorite(db_session, user.id, tenant.id)

        resp = client.delete(f"/api/prompts/favorites/{fav.id}", headers=_headers(user))

        assert resp.status_code == 200
        assert db_session.query(models.PromptFavorite).get(fav.id) is None

    def test_admin_sees_teammate_favorite_but_cannot_edit_it(self, client, db_session):
        tenant = _make_tenant(db_session)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)
        teammate = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        fav = _make_favorite(db_session, teammate.id, tenant.id, title="Teammate's")

        get_resp = client.get("/api/prompts/favorites", headers=_headers(admin))
        assert fav.id in {item["id"] for item in get_resp.json()}

        put_resp = client.put(
            f"/api/prompts/favorites/{fav.id}",
            json={"title": "Hijacked"},
            headers=_headers(admin),
        )
        assert put_resp.status_code == 403

    def test_admin_cannot_delete_teammate_favorite(self, client, db_session):
        tenant = _make_tenant(db_session)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)
        teammate = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        fav = _make_favorite(db_session, teammate.id, tenant.id)

        resp = client.delete(f"/api/prompts/favorites/{fav.id}", headers=_headers(admin))

        assert resp.status_code == 403
        assert db_session.query(models.PromptFavorite).get(fav.id) is not None

    def test_superadmin_cannot_edit_favorite_that_is_not_theirs(self, client, db_session):
        tenant = _make_tenant(db_session)
        superadmin = _make_user(db_session, models.UserRole.SUPERADMIN.value, None)
        cliente = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        fav = _make_favorite(db_session, cliente.id, tenant.id)

        resp = client.put(
            f"/api/prompts/favorites/{fav.id}",
            json={"title": "Overridden"},
            headers=_headers(superadmin),
        )

        assert resp.status_code == 403

    def test_cross_tenant_user_gets_404_not_403(self, client, db_session):
        """Sin visibilidad de lectura → 404, no 403 (no revela que el recurso existe)."""
        tenant_owner = _make_tenant(db_session)
        tenant_intruder = _make_tenant(db_session)
        owner = _make_user(db_session, models.UserRole.CLIENTE.value, tenant_owner.id)
        intruder = _make_user(db_session, models.UserRole.ADMIN.value, tenant_intruder.id)
        fav = _make_favorite(db_session, owner.id, tenant_owner.id)

        resp = client.put(
            f"/api/prompts/favorites/{fav.id}",
            json={"title": "Hijacked"},
            headers=_headers(intruder),
        )

        assert resp.status_code == 404

    def test_update_missing_favorite_returns_404(self, client, db_session):
        tenant = _make_tenant(db_session)
        user = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)

        resp = client.put(
            "/api/prompts/favorites/999999",
            json={"title": "X"},
            headers=_headers(user),
        )

        assert resp.status_code == 404


@pytest.mark.integration
class TestPortfolioDeleteNullsSourceJobId:
    """Regresión del fix agregado a delete_library_portfolio: sin él, borrar
    un job con favoritos apuntándolo revienta con IntegrityError (500)."""

    def test_deleting_source_job_orphans_favorite_instead_of_failing(self, client, db_session):
        tenant = _make_tenant(db_session)
        user = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        brand = models.Brand(name=f"Brand_{uuid.uuid4().hex}", tenant_id=tenant.id)
        db_session.add(brand)
        db_session.commit()
        db_session.refresh(brand)
        job = models.GenerationJob(
            brand_id=brand.id, owner_id=user.id, prompt="test",
            status=models.GenerationJobStatus.COMPLETED,
        )
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)
        fav = _make_favorite(db_session, user.id, tenant.id, source_job_id=job.id)

        resp = client.delete(f"/api/library/portfolios/{job.id}", headers=_headers(user))

        assert resp.status_code == 200
        db_session.refresh(fav)
        assert fav.source_job_id is None
