"""
test_seed_platform_bootstrap.py — seed_default_tenant() y el ajuste de
seed_test_users() para asociarse al tenant base en vez de crear el suyo
propio (decisión de Luis 2026-07-12: la DB debe quedar en un estado mínimo
y determinístico — superadmin + un tenant — para validar que todo se pueda
cargar bien desde cero).

Estos seeders commitean de verdad via SessionLocal() (no la
transacción-rollback de db_session) — mismo criterio que
test_data_alignments.py: fixture con limpieza explícita antes/después.
"""
import pytest

import models
from utils.seed_superadmin import DEFAULT_TENANT_NAME, seed_default_tenant
from utils.seed_test_users import seed_test_users


@pytest.fixture()
def bootstrap_db(create_test_schema, require_db):
    from database import SessionLocal
    db = SessionLocal()

    def _clean():
        # Deletes any user attached to the default tenant first, not just
        # "bootstrap.test.%" emails — main.py seeds for real at import time,
        # and on a local machine a bare load_dotenv() elsewhere in the app
        # (e.g. providers/llm_provider.py) can leak SUPERADMIN_EMAIL/
        # TEST_ADMIN_EMAIL from the repo-root .env into the test process the
        # first time some other test file does `from main import app`. That's
        # a pre-existing latent issue (unrelated to this feature, never
        # visible before because nothing asserted on seed_superadmin()'s
        # behavior) — this cleanup just needs to survive it, not fix it.
        tenant = db.query(models.Tenant).filter(models.Tenant.name == DEFAULT_TENANT_NAME).first()
        if tenant:
            db.query(models.User).filter(models.User.tenant_id == tenant.id).delete(synchronize_session=False)
        db.query(models.User).filter(models.User.email.like("bootstrap.test.%@example.com")).delete(synchronize_session=False)
        db.query(models.Tenant).filter(models.Tenant.name == DEFAULT_TENANT_NAME).delete(synchronize_session=False)
        db.commit()

    _clean()
    yield db
    _clean()
    db.close()


def _enable_superadmin_gate(monkeypatch):
    # seed_default_tenant() shares seed_superadmin()'s env-var gate on purpose
    # (see the comment in seed_superadmin.py) — without it, importing main.py
    # would silently create a real "Guepard" tenant in the test DB.
    monkeypatch.setenv("SUPERADMIN_EMAIL", "bootstrap.test.superadmin@example.com")
    monkeypatch.setenv("SUPERADMIN_PASSWORD", "irrelevant-password")


@pytest.mark.integration
class TestSeedDefaultTenant:

    def test_creates_the_tenant_once(self, bootstrap_db, monkeypatch):
        _enable_superadmin_gate(monkeypatch)
        seed_default_tenant()
        bootstrap_db.expire_all()
        matches = bootstrap_db.query(models.Tenant).filter(models.Tenant.name == DEFAULT_TENANT_NAME).all()
        assert len(matches) == 1

    def test_idempotent_second_call(self, bootstrap_db, monkeypatch):
        _enable_superadmin_gate(monkeypatch)
        seed_default_tenant()
        seed_default_tenant()
        bootstrap_db.expire_all()
        matches = bootstrap_db.query(models.Tenant).filter(models.Tenant.name == DEFAULT_TENANT_NAME).all()
        assert len(matches) == 1

    def test_skipped_without_superadmin_env_vars(self, bootstrap_db, monkeypatch):
        # Some services (e.g. providers/llm_provider.py) call a bare load_dotenv()
        # that can backfill these from the repo-root .env on a local machine —
        # clear explicitly so this test is deterministic regardless of that.
        monkeypatch.delenv("SUPERADMIN_EMAIL", raising=False)
        monkeypatch.delenv("SUPERADMIN_PASSWORD", raising=False)

        seed_default_tenant()
        bootstrap_db.expire_all()
        matches = bootstrap_db.query(models.Tenant).filter(models.Tenant.name == DEFAULT_TENANT_NAME).all()
        assert len(matches) == 0


@pytest.mark.integration
class TestSeedTestUsers:

    def test_attaches_admin_to_existing_default_tenant(self, bootstrap_db, monkeypatch):
        _enable_superadmin_gate(monkeypatch)
        seed_default_tenant()
        bootstrap_db.expire_all()
        tenant = bootstrap_db.query(models.Tenant).filter(models.Tenant.name == DEFAULT_TENANT_NAME).first()

        monkeypatch.setenv("TEST_ADMIN_EMAIL", "bootstrap.test.admin@example.com")
        monkeypatch.setenv("TEST_ADMIN_PASSWORD", "irrelevant-password")
        monkeypatch.delenv("TEST_CLIENTE_EMAIL", raising=False)
        monkeypatch.delenv("TEST_TENANT_NAME", raising=False)

        seed_test_users()

        bootstrap_db.expire_all()
        admin = bootstrap_db.query(models.User).filter(models.User.email == "bootstrap.test.admin@example.com").first()
        assert admin is not None
        assert admin.tenant_id == tenant.id

        # No spawns its own "Test Organization" tenant anymore.
        stray = bootstrap_db.query(models.Tenant).filter(models.Tenant.name == "Test Organization").first()
        assert stray is None

    def test_skips_without_default_tenant_seeded_yet(self, bootstrap_db, monkeypatch):
        # bootstrap_db's cleanup already ensures no "Guepard" tenant exists at this point.
        monkeypatch.setenv("TEST_ADMIN_EMAIL", "bootstrap.test.orphan@example.com")
        monkeypatch.setenv("TEST_ADMIN_PASSWORD", "irrelevant-password")
        monkeypatch.delenv("TEST_CLIENTE_EMAIL", raising=False)
        monkeypatch.delenv("TEST_TENANT_NAME", raising=False)

        seed_test_users()

        bootstrap_db.expire_all()
        admin = bootstrap_db.query(models.User).filter(models.User.email == "bootstrap.test.orphan@example.com").first()
        assert admin is None
