"""
backfill_visual_profiles.py — Regenera el perfil visual de assets existentes.

Las librerías ingestadas antes de la Iteración 1 de Selección de Imágenes no
tienen `visual_profile`. Este script lo genera con la misma llamada Vision que
usa la ingesta (run_vision_classification + build_visual_profile).

Uso (desde backend/, o dentro del contenedor con PYTHONPATH=/app):
    python utils/backfill_visual_profiles.py --brand-id 3
    python utils/backfill_visual_profiles.py --all
    python utils/backfill_visual_profiles.py --brand-id 3 --force   # regenera también los ya perfilados

Idempotente: sin --force solo procesa assets con visual_profile IS NULL.
Un fallo en un asset (p. ej. 429 de cuota) no aborta el lote; se reporta al final.
"""
import sys
import os
import argparse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
import models
from services.assets.asset_library_service import run_vision_classification, build_visual_profile


def resolve_asset_path(local_path: str, brand_id=None) -> str:
    """El local_path puede estar guardado como basename o como ruta completa."""
    from services.core.storage_service import resolve as resolve_storage
    return resolve_storage(local_path, brand_id=brand_id)


def backfill(brand_id: int = None, process_all: bool = False, force: bool = False) -> dict:
    db = SessionLocal()
    summary = {"processed": 0, "skipped": 0, "failed": 0, "file_missing": 0}
    try:
        query = db.query(models.BrandAsset).filter(models.BrandAsset.category != "noise")
        if not process_all:
            query = query.filter(models.BrandAsset.brand_id == brand_id)
        if not force:
            query = query.filter(models.BrandAsset.visual_profile.is_(None))

        assets = query.order_by(models.BrandAsset.id.asc()).all()
        total = len(assets)
        print(f"[Backfill] {total} asset(s) to process (brand={'ALL' if process_all else brand_id}, force={force})")

        for i, asset in enumerate(assets, start=1):
            file_path = resolve_asset_path(asset.local_path or "")
            if not file_path:
                summary["file_missing"] += 1
                print(f"  [{i}/{total}] Asset {asset.id}: file not found ({asset.local_path}) — skipped")
                continue

            try:
                vision_res = run_vision_classification(db, asset.brand_id, file_path)
                profile = build_visual_profile(vision_res)
                if profile:
                    asset.visual_profile = profile
                    db.commit()
                    summary["processed"] += 1
                    print(f"  [{i}/{total}] Asset {asset.id}: profile saved ({profile.get('orientation', '?')}, suitability={profile.get('layout_suitability', [])})")
                else:
                    summary["skipped"] += 1
                    print(f"  [{i}/{total}] Asset {asset.id}: vision returned no usable profile fields — left as NULL")
            except Exception as e:
                db.rollback()
                summary["failed"] += 1
                print(f"  [{i}/{total}] Asset {asset.id}: FAILED ({str(e)[:120]}) — left as NULL, safe to re-run")

        print(f"\n[Backfill] Done. processed={summary['processed']}, "
              f"no_profile={summary['skipped']}, failed={summary['failed']}, "
              f"file_missing={summary['file_missing']}")
        return summary
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill de visual_profile para BrandAsset.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--brand-id", type=int, help="ID de la marca a procesar")
    group.add_argument("--all", action="store_true", help="Procesar todas las marcas")
    parser.add_argument("--force", action="store_true", help="Regenerar también assets que ya tienen perfil")
    args = parser.parse_args()

    backfill(brand_id=args.brand_id, process_all=args.all, force=args.force)
