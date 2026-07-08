"""
test_data_alignments.py — Tests de Alineaciones de Datos Automáticas.

Cubre: estados y transiciones, claim atómico, no-reencolado de done, reintento
de failed, guard de configuración, fallo de encolado sin romper el dispatch,
alineación huérfana, y la alineación v1 (backfill de perfiles) mockeada.

Spec: docs/specs/alineaciones-de-datos.md
"""
import os
import pytest
from unittest.mock import MagicMock, patch

import models
from services.core.data_alignment_service import (
    ALIGNMENT_REGISTRY,
    dispatch_pending_alignments,
    run_alignment,
)


@pytest.fixture()
def alignment_db(create_test_schema, require_db):
    """
    Sesión REAL (SessionLocal → BD de test) con limpieza antes/después.
    El servicio commitea de verdad, así que no sirve la transacción-rollback
    de db_session. require_db: si la BD de test no está alcanzable, el test
    se salta con mensaje claro en vez de colgar en el connect (visto 2026-07-07
    con un .env.test apuntando a host.docker.internal inaccesible desde el host).
    """
    from database import SessionLocal
    db = SessionLocal()

    def _clean():
        db.query(models.DataAlignment).delete()
        db.query(models.SystemConfig).filter(
            models.SystemConfig.key == "auto_data_alignment_enabled"
        ).delete()
        db.commit()

    _clean()
    yield db
    _clean()
    db.close()


def _set_auto_enabled(db, value: str):
    db.add(models.SystemConfig(key="auto_data_alignment_enabled", value=value, description="test"))
    db.commit()


def _get_row(db, name):
    db.expire_all()
    return db.query(models.DataAlignment).filter(models.DataAlignment.name == name).first()


# ─────────────────────────────────────────────────────────────────────────────
# DISPATCH
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration
class TestDispatch:

    def test_creates_rows_and_enqueues_pending(self, alignment_db):
        mock_task = MagicMock()
        with patch("tasks.task_run_data_alignment", mock_task):
            summary = dispatch_pending_alignments()

        # Default sin config: habilitado. Aserciones por nombre — el registry
        # puede contener más alineaciones de otras iteraciones.
        assert summary["disabled"] is False
        assert "visual_profile_backfill_v1" in summary["enqueued"]
        enqueued_names = [c.args[0] for c in mock_task.delay.call_args_list]
        assert "visual_profile_backfill_v1" in enqueued_names
        row = _get_row(alignment_db, "visual_profile_backfill_v1")
        assert row is not None and row.status == "pending"

    def test_done_alignment_not_reenqueued(self, alignment_db):
        alignment_db.add(models.DataAlignment(name="visual_profile_backfill_v1", status="done"))
        alignment_db.commit()

        mock_task = MagicMock()
        with patch("tasks.task_run_data_alignment", mock_task):
            summary = dispatch_pending_alignments()

        enqueued_names = [c.args[0] for c in mock_task.delay.call_args_list]
        assert "visual_profile_backfill_v1" not in enqueued_names
        assert {"name": "visual_profile_backfill_v1", "status": "done"} in summary["skipped"]

    def test_failed_alignment_retried_on_next_boot(self, alignment_db):
        alignment_db.add(models.DataAlignment(name="visual_profile_backfill_v1", status="failed"))
        alignment_db.commit()

        mock_task = MagicMock()
        with patch("tasks.task_run_data_alignment", mock_task):
            summary = dispatch_pending_alignments()

        enqueued_names = [c.args[0] for c in mock_task.delay.call_args_list]
        assert "visual_profile_backfill_v1" in enqueued_names
        assert "visual_profile_backfill_v1" in summary["enqueued"]

    def test_guard_disabled_logs_but_does_not_enqueue(self, alignment_db):
        _set_auto_enabled(alignment_db, "false")

        mock_task = MagicMock()
        with patch("tasks.task_run_data_alignment", mock_task):
            summary = dispatch_pending_alignments()

        assert summary["disabled"] is True
        mock_task.delay.assert_not_called()
        # La fila se crea igual (queda visible como pendiente)
        assert _get_row(alignment_db, "visual_profile_backfill_v1").status == "pending"

    def test_enqueue_failure_does_not_break_dispatch(self, alignment_db):
        mock_task = MagicMock()
        mock_task.delay.side_effect = Exception("Redis is down")
        with patch("tasks.task_run_data_alignment", mock_task):
            summary = dispatch_pending_alignments()  # no debe lanzar

        assert summary["enqueued"] == []
        skipped_names = [s["name"] for s in summary["skipped"]]
        assert "visual_profile_backfill_v1" in skipped_names
        # Sigue pending → se reintenta en el siguiente arranque
        assert _get_row(alignment_db, "visual_profile_backfill_v1").status == "pending"

    def test_orphan_alignment_ignored(self, alignment_db):
        alignment_db.add(models.DataAlignment(name="legacy_alignment_v0", status="pending"))
        alignment_db.commit()

        with patch("tasks.task_run_data_alignment", MagicMock()):
            summary = dispatch_pending_alignments()

        assert "legacy_alignment_v0" in summary["orphans"]


# ─────────────────────────────────────────────────────────────────────────────
# RUN (claim atómico y transiciones)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration
class TestRunAlignment:

    def test_pending_runs_to_done_with_detail(self, alignment_db):
        alignment_db.add(models.DataAlignment(name="test_align_v1", status="pending"))
        alignment_db.commit()

        with patch.dict(ALIGNMENT_REGISTRY, {"test_align_v1": lambda: {"processed": 7, "failed": 0}}):
            result = run_alignment("test_align_v1")

        assert result["status"] == "done"
        row = _get_row(alignment_db, "test_align_v1")
        assert row.status == "done"
        assert '"processed": 7' in row.detail
        assert row.started_at is not None and row.finished_at is not None

    def test_running_alignment_cannot_be_claimed_twice(self, alignment_db):
        # Simula que otra réplica ya la tomó
        alignment_db.add(models.DataAlignment(name="test_align_v1", status="running"))
        alignment_db.commit()

        runner = MagicMock(return_value={})
        with patch.dict(ALIGNMENT_REGISTRY, {"test_align_v1": runner}):
            result = run_alignment("test_align_v1")

        assert result.get("skipped") is True
        runner.assert_not_called()
        assert _get_row(alignment_db, "test_align_v1").status == "running"

    def test_runner_exception_marks_failed_with_detail(self, alignment_db):
        alignment_db.add(models.DataAlignment(name="test_align_v1", status="pending"))
        alignment_db.commit()

        def _boom():
            raise RuntimeError("429 quota exceeded at asset 90/172")

        with patch.dict(ALIGNMENT_REGISTRY, {"test_align_v1": _boom}):
            result = run_alignment("test_align_v1")

        assert result["status"] == "failed"
        row = _get_row(alignment_db, "test_align_v1")
        assert row.status == "failed"
        assert "429 quota" in row.detail

    def test_unregistered_name_marks_failed_informative(self, alignment_db):
        alignment_db.add(models.DataAlignment(name="ghost_align_v9", status="pending"))
        alignment_db.commit()

        result = run_alignment("ghost_align_v9")

        assert result["status"] == "failed"
        assert "not in the registry" in _get_row(alignment_db, "ghost_align_v9").detail

    def test_visual_profile_backfill_v1_wired_to_backfill(self, alignment_db):
        alignment_db.add(models.DataAlignment(name="visual_profile_backfill_v1", status="pending"))
        alignment_db.commit()

        fake_summary = {"processed": 171, "skipped": 0, "failed": 1, "file_missing": 0}
        with patch("utils.backfill_visual_profiles.backfill", return_value=fake_summary) as mock_backfill:
            result = run_alignment("visual_profile_backfill_v1")

        mock_backfill.assert_called_once_with(process_all=True)
        assert result["status"] == "done"
        assert result["result"] == fake_summary
        assert _get_row(alignment_db, "visual_profile_backfill_v1").status == "done"


# ─────────────────────────────────────────────────────────────────────────────
# tenant_backfill_v1 (Autenticación / Multi-tenant — B1)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture()
def tenant_backfill_db(create_test_schema):
    """Sesión real (la alineación usa SessionLocal); limpia las filas que crea."""
    from database import SessionLocal
    db = SessionLocal()
    created = {"brands": [], "tenants": []}

    yield db, created

    for brand_id in created["brands"]:
        db.query(models.Brand).filter(models.Brand.id == brand_id).delete()
    for tenant_id in created["tenants"]:
        db.query(models.Tenant).filter(models.Tenant.id == tenant_id).delete()
    db.query(models.DataAlignment).filter(models.DataAlignment.name == "tenant_backfill_v1").delete()
    db.commit()
    db.close()


@pytest.mark.integration
class TestTenantBackfill:

    def _run(self):
        from services.core.data_alignment_service import _run_tenant_backfill
        return _run_tenant_backfill()

    def test_creates_legacy_tenant_and_assigns_brand(self, tenant_backfill_db):
        db, created = tenant_backfill_db
        brand = models.Brand(name=f"NoTenantBrand_{os.urandom(3).hex()}")
        db.add(brand)
        db.commit()
        created["brands"].append(brand.id)

        summary = self._run()

        assert summary["brands_assigned"] >= 1
        db.expire_all()
        refreshed = db.query(models.Brand).get(brand.id)
        assert refreshed.tenant_id is not None
        tenant = db.query(models.Tenant).get(refreshed.tenant_id)
        created["tenants"].append(tenant.id)
        assert tenant.name == f"{brand.name} (legacy)"

    def test_idempotent_second_run_skips_assigned_brands(self, tenant_backfill_db):
        db, created = tenant_backfill_db
        brand = models.Brand(name=f"IdempotentBrand_{os.urandom(3).hex()}")
        db.add(brand)
        db.commit()
        created["brands"].append(brand.id)

        self._run()
        db.expire_all()
        tenant_id_after_first_run = db.query(models.Brand).get(brand.id).tenant_id
        created["tenants"].append(tenant_id_after_first_run)

        self._run()

        db.expire_all()
        assert db.query(models.Brand).get(brand.id).tenant_id == tenant_id_after_first_run

    def test_leaves_already_tenant_scoped_brands_untouched(self, tenant_backfill_db):
        db, created = tenant_backfill_db
        tenant = models.Tenant(name="Pre-existing Tenant")
        db.add(tenant)
        db.commit()
        created["tenants"].append(tenant.id)

        brand = models.Brand(name=f"AlreadyScopedBrand_{os.urandom(3).hex()}", tenant_id=tenant.id)
        db.add(brand)
        db.commit()
        created["brands"].append(brand.id)

        self._run()

        db.expire_all()
        assert db.query(models.Brand).get(brand.id).tenant_id == tenant.id


# ─────────────────────────────────────────────────────────────────────────────
# ALINEACIÓN: stale_fallback_model_fix_v1 (Template Merge v2 Fase 2)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration
class TestStaleFallbackModelFix:

    STALE = "claude-3-5-sonnet-20241022"
    KEYS = ["extraction_synthesis_model", "global_fallback_model"]

    @pytest.fixture()
    def config_db(self, create_test_schema, require_db):
        from database import SessionLocal
        db = SessionLocal()

        def _clean():
            db.query(models.SystemConfig).filter(
                models.SystemConfig.key.in_(self.KEYS)
            ).delete(synchronize_session=False)
            db.commit()

        _clean()
        yield db
        _clean()
        db.close()

    def _run(self):
        from services.core.data_alignment_service import _run_stale_fallback_model_fix
        return _run_stale_fallback_model_fix()

    def test_replaces_stale_slug_in_both_chains(self, config_db):
        chain = f"mistral/mistral-large-latest,gemini-flash-latest,{self.STALE}"
        for key in self.KEYS:
            config_db.add(models.SystemConfig(key=key, value=chain, description="test"))
        config_db.commit()

        summary = self._run()

        assert sorted(summary["updated_keys"]) == sorted(self.KEYS)
        config_db.expire_all()
        for key in self.KEYS:
            value = config_db.query(models.SystemConfig).filter(models.SystemConfig.key == key).first().value
            assert self.STALE not in value
            assert "anthropic/claude-sonnet-4.6" in value

    def test_idempotent_and_leaves_clean_values_untouched(self, config_db):
        clean = "mistral/mistral-large-latest,anthropic/claude-sonnet-4.6"
        config_db.add(models.SystemConfig(key=self.KEYS[0], value=clean, description="test"))
        config_db.commit()

        summary = self._run()
        assert summary["updated_keys"] == []

        config_db.expire_all()
        row = config_db.query(models.SystemConfig).filter(models.SystemConfig.key == self.KEYS[0]).first()
        assert row.value == clean
