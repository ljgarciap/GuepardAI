"""
test_storage_service.py — Tests unitarios del StorageService (Fase 0).

Las raíces del servicio se redirigen a un árbol temporal vía monkeypatch para
no tocar uploads/outputs reales.

Spec: docs/specs/reorganizacion-storage.md
"""
import os
import time
import pytest

from services.core import storage_service as st


@pytest.fixture()
def storage_tree(tmp_path, monkeypatch):
    """Redirige TODAS las raíces del servicio a un árbol temporal aislado."""
    root = tmp_path / "storage"
    monkeypatch.setattr(st, "STORAGE_ROOT", str(root))
    monkeypatch.setattr(st, "PUBLIC_ROOT", str(root / "public"))
    monkeypatch.setattr(st, "PRIVATE_ROOT", str(root / "private"))
    monkeypatch.setattr(st, "TMP_ROOT", str(root / "tmp"))
    monkeypatch.setattr(st, "LEGACY_UPLOADS", str(tmp_path / "uploads"))
    monkeypatch.setattr(st, "LEGACY_OUTPUTS", str(tmp_path / "outputs"))
    return tmp_path


def _touch(path, content=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    return path


@pytest.mark.unit
class TestDirectories:

    def test_brand_dirs_created_and_segmented(self, storage_tree):
        assets = st.brand_assets_dir(7)
        sources = st.brand_sources_dir(7)
        assert os.path.isdir(assets) and assets.endswith(os.path.join("brands", "7", "assets"))
        assert os.path.isdir(sources) and "private" in sources

        # Sin marca: segmentos especiales
        assert st.PUBLIC_BRAND_SEGMENT in st.brand_assets_dir(None)
        assert st.UNASSIGNED_BRAND_SEGMENT in st.brand_sources_dir(None)

    def test_job_dir_and_tmp(self, storage_tree):
        jd = st.job_dir(42)
        assert os.path.isdir(jd) and jd.endswith(os.path.join("jobs", "42"))

        t1, t2 = st.tmp_path(".png"), st.tmp_path(".png")
        assert t1 != t2 and t1.endswith(".png")
        assert os.path.isdir(st.TMP_ROOT)


@pytest.mark.unit
class TestResolve:

    def test_resolves_absolute_path(self, storage_tree):
        f = _touch(str(storage_tree / "anywhere" / "img.png"))
        assert st.resolve(f) == os.path.abspath(f)

    def test_resolves_brand_asset_by_basename_with_context(self, storage_tree):
        f = _touch(os.path.join(st.brand_assets_dir(3), "photo.png"))
        assert st.resolve("photo.png", brand_id=3) == f

    def test_resolves_any_brand_asset_without_context(self, storage_tree):
        f = _touch(os.path.join(st.brand_assets_dir(9), "lonely.png"))
        assert st.resolve("lonely.png") == f

    def test_resolves_job_output_by_basename(self, storage_tree):
        f = _touch(os.path.join(st.job_dir(5), "deck.pptx"))
        assert st.resolve("deck.pptx") == f

    def test_resolves_legacy_uploads_and_outputs(self, storage_tree):
        legacy = _touch(os.path.join(st.LEGACY_UPLOADS, "old_asset.png"))
        assert st.resolve("old_asset.png") == legacy
        assert st.resolve("uploads/old_asset.png") == legacy  # ruta relativa histórica

        legacy_pdf = _touch(os.path.join(st.LEGACY_OUTPUTS, "artistic_pdf", "old.pdf"))
        assert st.resolve("old.pdf") == legacy_pdf

    def test_new_hierarchy_wins_over_legacy(self, storage_tree):
        _touch(os.path.join(st.LEGACY_UPLOADS, "both.png"), b"legacy")
        new = _touch(os.path.join(st.brand_assets_dir(1), "both.png"), b"new")
        assert st.resolve("both.png", brand_id=1) == new

    def test_missing_returns_none(self, storage_tree):
        assert st.resolve("ghost.png") is None
        assert st.resolve(None) is None
        assert st.resolve("") is None


@pytest.mark.unit
class TestPublicUrl:

    def test_public_tree_maps_to_files(self, storage_tree):
        f = _touch(os.path.join(st.brand_assets_dir(2), "img.png"))
        assert st.public_url(f) == "/files/brands/2/assets/img.png"

    def test_legacy_maps_to_uploads_and_outputs(self, storage_tree):
        up = _touch(os.path.join(st.LEGACY_UPLOADS, "img.png"))
        out = _touch(os.path.join(st.LEGACY_OUTPUTS, "deck.pdf"))
        assert st.public_url(up) == "/uploads/img.png"
        assert st.public_url(out) == "/outputs/deck.pdf"

    def test_private_and_tmp_are_never_servable(self, storage_tree):
        src = _touch(os.path.join(st.brand_sources_dir(2), "report.pdf"))
        tmp = _touch(st.tmp_path(".bin"))
        assert st.public_url(src) is None
        assert st.public_url(tmp) is None


@pytest.mark.unit
class TestMoveAndCleanup:

    def test_move_into_and_conflict_rename(self, storage_tree):
        dest_dir = st.brand_assets_dir(4)
        a = _touch(str(storage_tree / "src" / "same.png"), b"a")
        moved = st.move_into(a, dest_dir)
        assert moved == os.path.join(dest_dir, "same.png") and os.path.exists(moved)

        b = _touch(str(storage_tree / "src2" / "same.png"), b"b")
        moved_b = st.move_into(b, dest_dir, conflict_tag="77")
        assert moved_b.endswith("same_dup77.png")
        assert os.path.exists(moved) and os.path.exists(moved_b)

        assert st.move_into(str(storage_tree / "no" / "file.png"), dest_dir) is None

    def test_cleanup_tmp_removes_only_stale(self, storage_tree):
        stale = _touch(st.tmp_path(".old"))
        fresh = _touch(st.tmp_path(".new"))
        os.utime(stale, (time.time() - 90000, time.time() - 90000))  # ~25h

        removed = st.cleanup_tmp(older_than_hours=24)

        assert removed == 1
        assert not os.path.exists(stale)
        assert os.path.exists(fresh)
