"""
test_storage_migration.py — Integración de la Reorganización de Storage.

Cubre: la alineación file_reorganization_v1 (mover + actualizar BD,
idempotencia, huérfanos, ausentes), resolución de lectura tras el movimiento,
y el criterio de seguridad (private/ inaccesible por HTTP).

Spec: docs/specs/reorganizacion-storage.md
"""
import os
import pytest
from fastapi.testclient import TestClient

import models
from services.core import storage_service as st


@pytest.fixture()
def isolated_storage(tmp_path, monkeypatch):
    """Redirige raíces de storage Y legacy a un árbol temporal."""
    monkeypatch.setattr(st, "STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setattr(st, "PUBLIC_ROOT", str(tmp_path / "storage" / "public"))
    monkeypatch.setattr(st, "PRIVATE_ROOT", str(tmp_path / "storage" / "private"))
    monkeypatch.setattr(st, "TMP_ROOT", str(tmp_path / "storage" / "tmp"))
    monkeypatch.setattr(st, "LEGACY_UPLOADS", str(tmp_path / "uploads"))
    monkeypatch.setattr(st, "LEGACY_OUTPUTS", str(tmp_path / "outputs"))
    return tmp_path


@pytest.fixture()
def reorg_db(create_test_schema):
    """Sesión real (la alineación usa SessionLocal) con limpieza de filas propias."""
    from database import SessionLocal
    db = SessionLocal()
    created = {"assets": [], "jobs": [], "brands": [], "alignments": []}

    yield db, created

    for asset_id in created["assets"]:
        db.query(models.BrandAsset).filter(models.BrandAsset.id == asset_id).delete()
    for job_id in created["jobs"]:
        db.query(models.GenerationJob).filter(models.GenerationJob.id == job_id).delete()
    for brand_id in created["brands"]:
        db.query(models.Brand).filter(models.Brand.id == brand_id).delete()
    db.query(models.DataAlignment).filter(models.DataAlignment.name.like("file_reorg%")).delete()
    db.commit()
    db.close()


def _legacy_file(name, content=b"img"):
    path = os.path.join(st.LEGACY_UPLOADS, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# file_reorganization_v1
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration
class TestFileReorganization:

    def _run(self):
        from services.core.data_alignment_service import _run_file_reorganization
        return _run_file_reorganization()

    def test_moves_assets_and_updates_db(self, isolated_storage, reorg_db):
        db, created = reorg_db
        brand = models.Brand(name=f"ReorgBrand_{os.urandom(3).hex()}")
        db.add(brand); db.commit()
        created["brands"].append(brand.id)

        _legacy_file("reorg_photo.png")
        asset = models.BrandAsset(
            brand_id=brand.id, file_hash="r" * 64, local_path="reorg_photo.png",
            category="photos", description="reorg test", is_public=0,
        )
        db.add(asset); db.commit()
        created["assets"].append(asset.id)

        summary = self._run()

        assert summary["moved"] >= 1
        db.expire_all()
        moved_asset = db.query(models.BrandAsset).get(asset.id)
        # La ruta en BD ahora es relativa y apunta al árbol de la marca
        assert "storage/public/brands" in moved_asset.local_path.replace("\\", "/")
        physical = st.resolve(moved_asset.local_path, brand_id=brand.id)
        assert physical and os.path.exists(physical)
        assert not os.path.exists(os.path.join(st.LEGACY_UPLOADS, "reorg_photo.png"))

    def test_rerun_converges_to_zero_moves(self, isolated_storage, reorg_db):
        db, created = reorg_db
        brand = models.Brand(name=f"ReorgBrand2_{os.urandom(3).hex()}")
        db.add(brand); db.commit()
        created["brands"].append(brand.id)

        _legacy_file("converge.png")
        asset = models.BrandAsset(
            brand_id=brand.id, file_hash="c" * 64, local_path="converge.png",
            category="photos", description="converge test", is_public=0,
        )
        db.add(asset); db.commit()
        created["assets"].append(asset.id)

        first = self._run()
        second = self._run()

        assert first["moved"] >= 1
        assert second["moved"] == 0
        assert second["skipped"] >= 1  # ya bajo storage/

    def test_missing_file_reported_not_failed(self, isolated_storage, reorg_db):
        db, created = reorg_db
        asset = models.BrandAsset(
            brand_id=None, file_hash="m" * 64, local_path="ghost_never_existed.png",
            category="photos", description="missing test", is_public=1,
        )
        db.add(asset); db.commit()
        created["assets"].append(asset.id)

        summary = self._run()

        assert summary["missing"] >= 1
        assert summary["failed"] == 0

    def test_orphan_files_counted_but_not_moved(self, isolated_storage, reorg_db):
        orphan = _legacy_file("orphan_no_db_row.png")

        summary = self._run()

        assert summary["orphans"] >= 1
        assert os.path.exists(orphan)  # sigue en legacy, decisión humana

    def test_job_output_moves_to_job_dir(self, isolated_storage, reorg_db):
        db, created = reorg_db
        out = os.path.join(st.LEGACY_OUTPUTS, "old_deck.pptx")
        os.makedirs(st.LEGACY_OUTPUTS, exist_ok=True)
        with open(out, "wb") as f:
            f.write(b"pptx")

        job = models.GenerationJob(
            client_name="reorg", brand_id=0, prompt="t",
            status=models.GenerationJobStatus.COMPLETED, pptx_path="outputs/old_deck.pptx",
        )
        db.add(job); db.commit()
        created["jobs"].append(job.id)

        self._run()

        db.expire_all()
        moved_job = db.query(models.GenerationJob).get(job.id)
        assert f"jobs/{job.id}" in moved_job.pptx_path.replace("\\", "/")
        assert os.path.exists(os.path.join(st.job_dir(job.id), "old_deck.pptx"))


# ─────────────────────────────────────────────────────────────────────────────
# Lectura tras el movimiento (resolución centralizada en los renderers)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration
class TestReadAfterMove:

    def test_artistic_pdf_resolver_finds_moved_asset(self, isolated_storage):
        # WeasyPrint importa pero falla en hosts sin librerías GTK nativas (solo
        # disponibles en el contenedor/CI Linux); en ese caso se omite el test.
        try:
            from services.rendering.artistic_pdf_service import artistic_pdf_service
        except Exception as import_err:
            pytest.skip(f"render deps unavailable on this host: {import_err}")
        target = os.path.join(st.brand_assets_dir(8), "moved_hero.png")
        with open(target, "wb") as f:
            f.write(b"img")

        # Referencia histórica por basename (como queda en render_elements viejos)
        assert artistic_pdf_service._resolve_asset_path("moved_hero.png") == target

    def test_central_resolve_finds_moved_asset_by_basename(self, isolated_storage):
        # Mismo comportamiento, sin dependencias de render: es lo que
        # _resolve_asset_path delega desde la migración a resolve()
        target = os.path.join(st.brand_assets_dir(8), "moved_hero2.png")
        with open(target, "wb") as f:
            f.write(b"img")

        assert st.resolve("moved_hero2.png") == target

    def test_backfill_resolver_uses_central_resolve(self, isolated_storage):
        from utils.backfill_visual_profiles import resolve_asset_path
        target = os.path.join(st.brand_assets_dir(9), "profiled.png")
        with open(target, "wb") as f:
            f.write(b"img")

        assert resolve_asset_path("profiled.png", brand_id=9) == target


# ─────────────────────────────────────────────────────────────────────────────
# Seguridad: private/ jamás accesible por HTTP (montajes REALES, sin monkeypatch)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration
class TestPrivateTreeSecurity:

    def test_private_sources_not_served(self):
        from main import app
        secret = os.path.join(st.PRIVATE_ROOT, "brands", "999", "sources")
        os.makedirs(secret, exist_ok=True)
        secret_file = os.path.join(secret, "confidential_report.pdf")
        with open(secret_file, "wb") as f:
            f.write(b"secret")

        try:
            client = TestClient(app)
            attempts = [
                "/files/brands/999/sources/confidential_report.pdf",
                "/files/../private/brands/999/sources/confidential_report.pdf",
                "/uploads/../storage/private/brands/999/sources/confidential_report.pdf",
                "/outputs/../storage/private/brands/999/sources/confidential_report.pdf",
            ]
            for url in attempts:
                res = client.get(url)
                assert res.status_code == 404, f"PRIVATE LEAK via {url} (status {res.status_code})"
        finally:
            os.remove(secret_file)

    def test_public_tree_is_served(self):
        from main import app
        public_dir = os.path.join(st.PUBLIC_ROOT, "brands", "999", "assets")
        os.makedirs(public_dir, exist_ok=True)
        public_file = os.path.join(public_dir, "servable.png")
        with open(public_file, "wb") as f:
            f.write(b"public img")

        try:
            client = TestClient(app)
            res = client.get("/files/brands/999/assets/servable.png")
            assert res.status_code == 200
            assert res.content == b"public img"
        finally:
            os.remove(public_file)
