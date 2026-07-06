"""
test_auth_dependencies.py — get_current_user, require_role, require_tenant_access,
check_login_rate_limit (B3).

Usa `db_session` (transacción con rollback) porque estas dependencias solo
leen — no hay riesgo de dejar datos ni necesidad de limpieza manual.

Spec: docs/specs/autenticacion-multiusuario-multitenant.md
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from jose import jwt

import models
from auth import security
from auth.dependencies import (
    check_login_rate_limit,
    get_current_user,
    require_role,
    require_tenant_access,
)


def _make_user(db, role, tenant_id=None, is_active=1, email=None):
    user = models.User(
        email=email or f"{role}_{id(object())}@example.com",
        hashed_password=security.hash_password("irrelevant-password"),
        role=role,
        tenant_id=tenant_id,
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _fake_request(ip="127.0.0.1"):
    return SimpleNamespace(client=SimpleNamespace(host=ip))


@pytest.mark.integration
class TestGetCurrentUser:

    def test_valid_access_token_returns_user(self, db_session):
        user = _make_user(db_session, models.UserRole.ADMIN.value, tenant_id=None)
        token = security.create_access_token(user.id, user.role, user.tenant_id)

        result = get_current_user(token=token, db=db_session)

        assert result.id == user.id

    def test_no_token_raises_401(self, db_session):
        with pytest.raises(HTTPException) as exc:
            get_current_user(token=None, db=db_session)
        assert exc.value.status_code == 401

    def test_garbage_token_raises_401(self, db_session):
        with pytest.raises(HTTPException) as exc:
            get_current_user(token="not-a-jwt", db=db_session)
        assert exc.value.status_code == 401

    def test_refresh_token_used_as_access_raises_401(self, db_session):
        user = _make_user(db_session, models.UserRole.CLIENTE.value, tenant_id=None)
        refresh_token, _, _ = security.create_refresh_token(user.id)

        with pytest.raises(HTTPException) as exc:
            get_current_user(token=refresh_token, db=db_session)
        assert exc.value.status_code == 401

    def test_inactive_user_raises_401(self, db_session):
        user = _make_user(db_session, models.UserRole.CLIENTE.value, tenant_id=None, is_active=0)
        token = security.create_access_token(user.id, user.role, user.tenant_id)

        with pytest.raises(HTTPException) as exc:
            get_current_user(token=token, db=db_session)
        assert exc.value.status_code == 401

    def test_deleted_user_id_raises_401(self, db_session):
        token = security.create_access_token(user_id=999999, role="cliente", tenant_id=None)

        with pytest.raises(HTTPException) as exc:
            get_current_user(token=token, db=db_session)
        assert exc.value.status_code == 401


@pytest.mark.integration
class TestRequireRole:

    def test_matching_role_passes(self, db_session):
        user = _make_user(db_session, models.UserRole.ADMIN.value, tenant_id=None)
        checker = require_role(models.UserRole.ADMIN.value, models.UserRole.SUPERADMIN.value)

        assert checker(user=user).id == user.id

    def test_non_matching_role_raises_403(self, db_session):
        user = _make_user(db_session, models.UserRole.CLIENTE.value, tenant_id=None)
        checker = require_role(models.UserRole.ADMIN.value, models.UserRole.SUPERADMIN.value)

        with pytest.raises(HTTPException) as exc:
            checker(user=user)
        assert exc.value.status_code == 403


@pytest.mark.integration
class TestRequireTenantAccess:

    def test_superadmin_bypasses_any_tenant(self, db_session):
        tenant_a = models.Tenant(name="Tenant A")
        db_session.add(tenant_a); db_session.commit()
        brand = models.Brand(name=f"BrandA_{id(object())}", tenant_id=tenant_a.id)
        db_session.add(brand); db_session.commit()

        superadmin = _make_user(db_session, models.UserRole.SUPERADMIN.value, tenant_id=None)

        result = require_tenant_access(brand_id=brand.id, db=db_session, user=superadmin)
        assert result.id == superadmin.id

    def test_admin_same_tenant_passes(self, db_session):
        tenant = models.Tenant(name="Tenant Same")
        db_session.add(tenant); db_session.commit()
        brand = models.Brand(name=f"BrandSame_{id(object())}", tenant_id=tenant.id)
        db_session.add(brand); db_session.commit()

        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant_id=tenant.id)

        result = require_tenant_access(brand_id=brand.id, db=db_session, user=admin)
        assert result.id == admin.id

    def test_cliente_other_tenant_raises_403(self, db_session):
        tenant_owner = models.Tenant(name="Owner Tenant")
        tenant_intruder = models.Tenant(name="Intruder Tenant")
        db_session.add_all([tenant_owner, tenant_intruder]); db_session.commit()
        brand = models.Brand(name=f"BrandOwned_{id(object())}", tenant_id=tenant_owner.id)
        db_session.add(brand); db_session.commit()

        intruder = _make_user(db_session, models.UserRole.CLIENTE.value, tenant_id=tenant_intruder.id)

        with pytest.raises(HTTPException) as exc:
            require_tenant_access(brand_id=brand.id, db=db_session, user=intruder)
        assert exc.value.status_code == 403

    def test_brand_not_found_raises_404(self, db_session):
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant_id=None)

        with pytest.raises(HTTPException) as exc:
            require_tenant_access(brand_id=999999, db=db_session, user=admin)
        assert exc.value.status_code == 404

    def test_brand_without_tenant_denies_admin(self, db_session):
        """Brand pre-backfill (tenant_id IS NULL) — denegado, no bypass incidental."""
        brand = models.Brand(name=f"BrandNoTenant_{id(object())}", tenant_id=None)
        db_session.add(brand); db_session.commit()
        admin = _make_user(db_session, models.UserRole.ADMIN.value, tenant_id=None)

        with pytest.raises(HTTPException) as exc:
            require_tenant_access(brand_id=brand.id, db=db_session, user=admin)
        assert exc.value.status_code == 403


@pytest.mark.unit
class TestLoginRateLimit:

    def test_under_threshold_does_not_raise(self, monkeypatch):
        fake_redis = MagicMock()
        fake_redis.incr.return_value = 1
        monkeypatch.setattr("auth.dependencies.get_redis_client", lambda: fake_redis)

        check_login_rate_limit(_fake_request(), "user@example.com")  # no debe lanzar
        fake_redis.expire.assert_called_once()

    def test_over_threshold_raises_429(self, monkeypatch):
        fake_redis = MagicMock()
        fake_redis.incr.return_value = 6  # > LOGIN_RATE_LIMIT_MAX_ATTEMPTS (5 default)
        monkeypatch.setattr("auth.dependencies.get_redis_client", lambda: fake_redis)

        with pytest.raises(HTTPException) as exc:
            check_login_rate_limit(_fake_request(), "user@example.com")
        assert exc.value.status_code == 429

    def test_redis_down_fails_open(self, monkeypatch):
        fake_redis = MagicMock()
        fake_redis.incr.side_effect = Exception("connection refused")
        monkeypatch.setattr("auth.dependencies.get_redis_client", lambda: fake_redis)

        check_login_rate_limit(_fake_request(), "user@example.com")  # no debe lanzar
