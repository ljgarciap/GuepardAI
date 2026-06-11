"""
storage_service.py — Único punto de verdad del layout físico de archivos.

Jerarquía (Reorganización de Storage, Fase 0/1):

    backend/storage/
      public/                      # único árbol servible por HTTP (/files)
        brands/{brand_id}/assets/  # assets extraídos + generados por IA
        jobs/{job_id}/             # outputs finales del job
      private/
        brands/{brand_id}/sources/ # documentos subidos — NUNCA servidos
      tmp/                         # intermedios, limpiables (>24h)

Legacy (fallback de LECTURA hasta la Fase 3): backend/uploads y backend/outputs.

REGLA DEL PROYECTO: ningún módulo fuera de este servicio construye rutas con
os.path.join("uploads", ...) ni recorre candidatos a mano — usar resolve().

Spec: docs/specs/reorganizacion-storage.md
Design: docs/designs/reorganizacion-storage.md
"""
import glob
import logging
import os
import shutil
import time
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

# services/core/ → backend/
BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

STORAGE_ROOT = os.path.join(BACKEND_ROOT, "storage")
PUBLIC_ROOT = os.path.join(STORAGE_ROOT, "public")
PRIVATE_ROOT = os.path.join(STORAGE_ROOT, "private")
TMP_ROOT = os.path.join(STORAGE_ROOT, "tmp")

LEGACY_UPLOADS = os.path.join(BACKEND_ROOT, "uploads")
LEGACY_OUTPUTS = os.path.join(BACKEND_ROOT, "outputs")

PUBLIC_BRAND_SEGMENT = "_public"      # assets is_public sin marca propietaria
UNASSIGNED_BRAND_SEGMENT = "_unassigned"


def _ensure(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def _id_segment(value, fallback: str) -> str:
    """Segmento de carpeta seguro: solo ids enteros; cualquier otra cosa → fallback."""
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return fallback


def brand_assets_dir(brand_id) -> str:
    """public/brands/{id}/assets — assets de imagen de la marca (servibles)."""
    return _ensure(os.path.join(PUBLIC_ROOT, "brands", _id_segment(brand_id, PUBLIC_BRAND_SEGMENT), "assets"))


def brand_sources_dir(brand_id) -> str:
    """private/brands/{id}/sources — documentos subidos (NUNCA servidos)."""
    return _ensure(os.path.join(PRIVATE_ROOT, "brands", _id_segment(brand_id, UNASSIGNED_BRAND_SEGMENT), "sources"))


def job_dir(job_id) -> str:
    """public/jobs/{id} — outputs finales del job."""
    return _ensure(os.path.join(PUBLIC_ROOT, "jobs", _id_segment(job_id, "_unknown")))


def tmp_path(suffix: str = "") -> str:
    """Ruta única bajo storage/tmp (no crea el archivo)."""
    _ensure(TMP_ROOT)
    return os.path.join(TMP_ROOT, f"{uuid.uuid4().hex}{suffix}")


def to_relative(abs_path: str) -> str:
    """Ruta relativa a backend/ para persistir en BD (portable host/contenedor)."""
    try:
        return os.path.relpath(os.path.abspath(abs_path), BACKEND_ROOT).replace("\\", "/")
    except ValueError:
        # Distinta unidad en Windows: persistir absoluta como último recurso
        return os.path.abspath(abs_path).replace("\\", "/")


def public_url(path: str) -> Optional[str]:
    """
    URL servible para una ruta física: /files/... (jerarquía nueva),
    /uploads/... o /outputs/... (legacy). None si no es servible (private/tmp).
    """
    if not path:
        return None
    abs_path = path if os.path.isabs(path) else os.path.join(BACKEND_ROOT, path)
    abs_path = os.path.abspath(abs_path)

    for root, prefix in ((PUBLIC_ROOT, "/files"), (LEGACY_UPLOADS, "/uploads"), (LEGACY_OUTPUTS, "/outputs")):
        try:
            rel = os.path.relpath(abs_path, root)
        except ValueError:
            continue
        if not rel.startswith(".."):
            return f"{prefix}/{rel.replace(os.sep, '/')}"
    return None


def resolve(ref, brand_id=None) -> Optional[str]:
    """
    Resuelve cualquier referencia histórica o nueva a una ruta física existente.

    Acepta: ruta absoluta, ruta relativa (a cwd o a backend/) o solo basename.
    Orden: (1) la ref tal cual, (2) assets de la marca si hay contexto,
    (3) assets de cualquier marca, (4) outputs de jobs, (5) legacy
    uploads/outputs. Devuelve None si no existe en ninguna ubicación.
    """
    if not ref:
        return None
    ref = str(ref)

    # 1. Ruta directa (absoluta, relativa a cwd, o relativa a backend/)
    for candidate in (ref, os.path.join(BACKEND_ROOT, ref)):
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)

    basename = os.path.basename(ref.replace("\\", "/"))
    if not basename:
        return None

    # 2. Assets de la marca en contexto
    if brand_id:
        candidate = os.path.join(PUBLIC_ROOT, "brands", str(brand_id), "assets", basename)
        if os.path.isfile(candidate):
            return candidate

    # 3. Assets de cualquier marca (árbol pequeño por diseño)
    matches = glob.glob(os.path.join(PUBLIC_ROOT, "brands", "*", "assets", basename))
    if matches:
        return matches[0]

    # 3b. Documentos fuente (resolución interna; public_url() los rechaza igual)
    if brand_id:
        candidate = os.path.join(PRIVATE_ROOT, "brands", str(brand_id), "sources", basename)
        if os.path.isfile(candidate):
            return candidate
    matches = glob.glob(os.path.join(PRIVATE_ROOT, "brands", "*", "sources", basename))
    if matches:
        return matches[0]

    # 4. Outputs de jobs
    matches = glob.glob(os.path.join(PUBLIC_ROOT, "jobs", "*", basename))
    if matches:
        return matches[0]

    # 5. Legacy (Fase 3 retirará este bloque)
    for legacy_dir in (LEGACY_UPLOADS, LEGACY_OUTPUTS, os.path.join(LEGACY_OUTPUTS, "artistic_pdf")):
        candidate = os.path.join(legacy_dir, basename)
        if os.path.isfile(candidate):
            return candidate

    return None


def move_into(src_path: str, dest_dir: str, conflict_tag: str = None) -> Optional[str]:
    """
    Mueve un archivo a dest_dir (para la alineación de migración).
    Colisión con archivo distinto → renombra con sufijo conflict_tag.
    Devuelve la ruta final o None si el origen no existe.
    """
    if not src_path or not os.path.isfile(src_path):
        return None
    _ensure(dest_dir)
    basename = os.path.basename(src_path)
    dest = os.path.join(dest_dir, basename)

    if os.path.abspath(dest) == os.path.abspath(src_path):
        return dest
    if os.path.exists(dest):
        stem, ext = os.path.splitext(basename)
        tag = conflict_tag or uuid.uuid4().hex[:8]
        dest = os.path.join(dest_dir, f"{stem}_dup{tag}{ext}")

    shutil.move(src_path, dest)
    return dest


def cleanup_tmp(older_than_hours: int = 24) -> int:
    """Elimina temporales antiguos. Tolerante: nunca lanza."""
    removed = 0
    try:
        if not os.path.isdir(TMP_ROOT):
            return 0
        cutoff = time.time() - older_than_hours * 3600
        for name in os.listdir(TMP_ROOT):
            path = os.path.join(TMP_ROOT, name)
            try:
                if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                    os.remove(path)
                    removed += 1
            except Exception:
                pass
        if removed:
            logger.info(f"[Storage] tmp housekeeping: {removed} stale file(s) removed.")
    except Exception as e:
        logger.warning(f"[Storage] tmp housekeeping skipped: {e}")
    return removed
