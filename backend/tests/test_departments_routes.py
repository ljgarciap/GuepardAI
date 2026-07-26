"""
test_departments_routes.py — /api/admin/departments, /api/users/{id}/department,
/api/users/directory (reviews-analitica-colaboracion, ítem 4).

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
    from services.core.auth_service import get_current_tos_version
    user = models.User(
        email=email or f"{role}_{uuid.uuid4().hex}@example.com",
        hashed_password=security.hash_password("irrelevant-password"),
        role=role,
        tenant_id=tenant_id,
        is_active=1,
        # Estas rutas no prueban el gate de ToS (auth/dependencies.py) — se
        # asume aceptado para no acoplar tests de departamentos a esa feature.
        tos_accepted=1,
        tos_accepted_version=get_current_tos_version(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_department(db, tenant_id, name=None):
    dept = models.Department(tenant_id=tenant_id, name=name or f"Dept_{uuid.uuid4().hex}")
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


def _headers(user):
    token = security.create_access_token(user.id, user.role, user.tenant_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
class TestCreateDepartment:

    def test_admin_creates_department_in_own_tenant(self, client, db_session):
        tenant = _make_tenant(db_session)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)

        resp = client.post("/api/admin/departments", json={"name": "Sales"}, headers=_headers(admin))
        assert resp.status_code == 201
        assert resp.json()["tenant_id"] == tenant.id
        assert resp.json()["name"] == "Sales"

    def test_superadmin_requires_explicit_tenant_id(self, client, db_session, superadmin_headers):
        resp = client.post("/api/admin/departments", json={"name": "NoTenant"}, headers=superadmin_headers)
        assert resp.status_code == 422

    def test_superadmin_creates_for_specified_tenant(self, client, db_session, superadmin_headers):
        tenant = _make_tenant(db_session)
        resp = client.post("/api/admin/departments", json={"name": "Eng", "tenant_id": tenant.id}, headers=superadmin_headers)
        assert resp.status_code == 201
        assert resp.json()["tenant_id"] == tenant.id

    def test_duplicate_name_in_same_tenant_conflicts(self, client, db_session):
        tenant = _make_tenant(db_session)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)
        client.post("/api/admin/departments", json={"name": "Sales"}, headers=_headers(admin))

        resp = client.post("/api/admin/departments", json={"name": "Sales"}, headers=_headers(admin))
        assert resp.status_code == 409

    def test_cliente_forbidden(self, client, db_session):
        tenant = _make_tenant(db_session)
        cliente = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)

        resp = client.post("/api/admin/departments", json={"name": "Sales"}, headers=_headers(cliente))
        assert resp.status_code == 403


@pytest.mark.integration
class TestListDepartments:

    def test_admin_sees_only_own_tenant(self, client, db_session):
        tenant_a = _make_tenant(db_session, "A")
        tenant_b = _make_tenant(db_session, "B")
        admin_a = _make_user(db_session, models.UserRole.ADMIN.value, tenant_a.id)
        _make_department(db_session, tenant_a.id, "InTenantA")
        _make_department(db_session, tenant_b.id, "InTenantB")

        resp = client.get("/api/admin/departments", headers=_headers(admin_a))
        names = {d["name"] for d in resp.json()}
        assert "InTenantA" in names
        assert "InTenantB" not in names

    def test_superadmin_can_filter_by_tenant_id(self, client, db_session, superadmin_headers):
        tenant_a = _make_tenant(db_session, "A2")
        tenant_b = _make_tenant(db_session, "B2")
        _make_department(db_session, tenant_a.id, "DeptA2")
        _make_department(db_session, tenant_b.id, "DeptB2")

        resp = client.get(f"/api/admin/departments?tenant_id={tenant_a.id}", headers=superadmin_headers)
        names = {d["name"] for d in resp.json()}
        assert names == {"DeptA2"}

    def test_department_includes_tenant_name(self, client, db_session):
        tenant = _make_tenant(db_session, "NamedTenant")
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)
        _make_department(db_session, tenant.id, "WithTenantName")

        resp = client.get("/api/admin/departments", headers=_headers(admin))
        entry = next(d for d in resp.json() if d["name"] == "WithTenantName")
        assert entry["tenant_name"] == tenant.name


@pytest.mark.integration
class TestDeleteDepartment:

    def test_delete_empty_department_succeeds(self, client, db_session):
        tenant = _make_tenant(db_session)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)
        dept = _make_department(db_session, tenant.id)

        resp = client.delete(f"/api/admin/departments/{dept.id}", headers=_headers(admin))
        assert resp.status_code == 200

    def test_delete_department_with_users_conflicts(self, client, db_session):
        tenant = _make_tenant(db_session)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)
        dept = _make_department(db_session, tenant.id)
        member = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        member.department_id = dept.id
        db_session.commit()

        resp = client.delete(f"/api/admin/departments/{dept.id}", headers=_headers(admin))
        assert resp.status_code == 409

    def test_delete_cross_tenant_department_forbidden(self, client, db_session):
        tenant_a = _make_tenant(db_session, "A3")
        tenant_b = _make_tenant(db_session, "B3")
        admin_a = _make_user(db_session, models.UserRole.ADMIN.value, tenant_a.id)
        dept_b = _make_department(db_session, tenant_b.id)

        resp = client.delete(f"/api/admin/departments/{dept_b.id}", headers=_headers(admin_a))
        assert resp.status_code == 403

    def test_delete_nonexistent_department_404(self, client, db_session):
        tenant = _make_tenant(db_session)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)

        resp = client.delete("/api/admin/departments/999999", headers=_headers(admin))
        assert resp.status_code == 404


@pytest.mark.integration
class TestUpdateUserDepartment:

    def test_admin_assigns_department_to_user(self, client, db_session):
        tenant = _make_tenant(db_session)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)
        member = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        dept = _make_department(db_session, tenant.id)

        resp = client.patch(f"/api/users/{member.id}/department", json={"department_id": dept.id}, headers=_headers(admin))
        assert resp.status_code == 200
        assert resp.json()["department_id"] == dept.id

    def test_clearing_department_sets_null(self, client, db_session):
        tenant = _make_tenant(db_session)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)
        dept = _make_department(db_session, tenant.id)
        member = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        member.department_id = dept.id
        db_session.commit()

        resp = client.patch(f"/api/users/{member.id}/department", json={"department_id": None}, headers=_headers(admin))
        assert resp.status_code == 200
        assert resp.json()["department_id"] is None

    def test_department_from_different_tenant_rejected(self, client, db_session):
        tenant_a = _make_tenant(db_session, "A4")
        tenant_b = _make_tenant(db_session, "B4")
        admin_a = _make_user(db_session, models.UserRole.ADMIN.value, tenant_a.id)
        member_a = _make_user(db_session, models.UserRole.CLIENTE.value, tenant_a.id)
        dept_b = _make_department(db_session, tenant_b.id)

        resp = client.patch(f"/api/users/{member_a.id}/department", json={"department_id": dept_b.id}, headers=_headers(admin_a))
        assert resp.status_code == 403

    def test_nonexistent_department_404(self, client, db_session):
        tenant = _make_tenant(db_session)
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant.id)
        member = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)

        resp = client.patch(f"/api/users/{member.id}/department", json={"department_id": 999999}, headers=_headers(admin))
        assert resp.status_code == 404

    def test_cross_tenant_target_user_forbidden(self, client, db_session):
        tenant_a = _make_tenant(db_session, "A5")
        tenant_b = _make_tenant(db_session, "B5")
        admin_a = _make_user(db_session, models.UserRole.ADMIN.value, tenant_a.id)
        member_b = _make_user(db_session, models.UserRole.CLIENTE.value, tenant_b.id)

        resp = client.patch(f"/api/users/{member_b.id}/department", json={"department_id": None}, headers=_headers(admin_a))
        assert resp.status_code == 403


@pytest.mark.integration
class TestUserDirectory:

    def test_cliente_can_call_directory(self, client, db_session):
        """A diferencia de GET /api/users (admin-only), cualquier usuario autenticado
        puede ver el directorio mínimo — un owner `cliente` necesita poder invitar."""
        tenant = _make_tenant(db_session)
        cliente = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id)
        peer = _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id, email="peer@example.com")

        resp = client.get("/api/users/directory", headers=_headers(cliente))
        assert resp.status_code == 200
        emails = {u["email"] for u in resp.json()}
        assert "peer@example.com" in emails
        # Shape mínimo: solo id+email, no role/tenant_id/is_active
        assert set(resp.json()[0].keys()) == {"id", "email"}

    def test_directory_scoped_to_own_tenant(self, client, db_session):
        tenant_a = _make_tenant(db_session, "A6")
        tenant_b = _make_tenant(db_session, "B6")
        cliente_a = _make_user(db_session, models.UserRole.CLIENTE.value, tenant_a.id)
        _make_user(db_session, models.UserRole.CLIENTE.value, tenant_b.id, email="other.tenant@example.com")

        resp = client.get("/api/users/directory", headers=_headers(cliente_a))
        emails = {u["email"] for u in resp.json()}
        assert "other.tenant@example.com" not in emails

    def test_superadmin_sees_all_in_directory(self, client, db_session, superadmin_headers):
        tenant = _make_tenant(db_session, "A7")
        _make_user(db_session, models.UserRole.CLIENTE.value, tenant.id, email="visible.to.superadmin@example.com")

        resp = client.get("/api/users/directory", headers=superadmin_headers)
        emails = {u["email"] for u in resp.json()}
        assert "visible.to.superadmin@example.com" in emails
