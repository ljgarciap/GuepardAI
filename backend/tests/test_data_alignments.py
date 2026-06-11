"""
test_data_alignments.py — Tests de Alineaciones de Datos Automáticas.

Cubre: estados y transiciones, claim atómico, no-reencolado de done, reintento
de failed, guard de configuración, fallo de encolado sin romper el dispatch,
alineación huérfana, y la alineación v1 (backfill de perfiles) mockeada.

Spec: docs/specs/alineaciones-de-datos.md
"""
import pytest
from unittest.mock import MagicMock, patch

import models
from services.core.data_alignment_service import (
    ALIGNMENT_REGISTRY,
    dispatch_pending_alignments,
    run_alignment,
)


@pytest.fixture()
def alignment_db(create_test_schema):
    """
    Sesión REAL (SessionLocal → BD de test) con limpieza antes/después.
    El servicio commitea de verdad, así que no sirve la transacción-rollback
    de db_session.
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

        # Default sin config: habilitado
        assert summary["disabled"] is False
        assert "visual_profile_backfill_v1" in summary["enqueued"]
        mock_task.delay.assert_called_once_with("visual_profile_backfill_v1")
        row = _get_row(alignment_db, "visual_profile_backfill_v1")
        assert row is not None and row.status == "pending"

    def test_done_alignment_not_reenqueued(self, alignment_db):
        alignment_db.add(models.DataAlignment(name="visual_profile_backfill_v1", status="done"))
        alignment_db.commit()

        mock_task = MagicMock()
        with patch("tasks.task_run_data_alignment", mock_task):
            summary = dispatch_pending_alignments()

        mock_task.delay.assert_not_called()
        assert {"name": "visual_profile_backfill_v1", "status": "done"} in summary["skipped"]

    def test_failed_alignment_retried_on_next_boot(self, alignment_db):
        alignment_db.add(models.DataAlignment(name="visual_profile_backfill_v1", status="failed"))
        alignment_db.commit()

        mock_task = MagicMock()
        with patch("tasks.task_run_data_alignment", mock_task):
            summary = dispatch_pending_alignments()

        mock_task.delay.assert_called_once_with("visual_profile_backfill_v1")
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
