# Design: Reorganización Jerárquica del Storage

**Date**: 2026-06-11
**Architect**: aprobado
**Spec**: `docs/specs/reorganizacion-storage.md`
**Status**: Approved — listo para desglose del PM
**Rama**: `feature/storage-reorganization`

## StorageService (`services/core/storage_service.py`)

Único módulo que conoce el layout físico. Constantes de raíz derivadas de
`backend/` (mismo criterio que `UPLOAD_DIR` actual).

```python
STORAGE_ROOT   = <backend>/storage
PUBLIC_ROOT    = storage/public
PRIVATE_ROOT   = storage/private
TMP_ROOT       = storage/tmp
LEGACY_UPLOADS = <backend>/uploads      # fallback de lectura
LEGACY_OUTPUTS = <backend>/outputs      # fallback de lectura

def brand_assets_dir(brand_id) -> str      # public/brands/{id}/assets (mkdir)
def brand_sources_dir(brand_id) -> str     # private/brands/{id}/sources (mkdir)
def job_dir(job_id) -> str                 # public/jobs/{id} (mkdir)
def tmp_path(suffix="") -> str             # storage/tmp/<uuid><suffix>
def public_url(abs_path) -> str | None     # ruta bajo public/ → "/files/..."; legacy uploads → "/uploads/..."

def resolve(ref, brand_id=None) -> str | None:
    # 1. ref absoluta/relativa existente → ruta
    # 2. basename en public/brands/{brand_id}/assets si hay contexto de marca
    # 3. basename en public/brands/*/assets (glob acotado)
    # 4. legacy: uploads/<basename>, backend/uploads/<basename>, outputs/<basename>
    # 5. None
```

- `resolve()` reemplaza el patrón "candidates" en los ~15 sitios. Donde hoy
  existe contexto de marca (art director, backfill) se pasa `brand_id` para el
  atajo del paso 2.
- `_resolve_asset_dims` (art_director) y los resolvers de `pptx_renderer`,
  `painter`, `layout_engine`, `vision_layout_engine`, `painter_bridge`,
  `artistic_pdf_service`, `asset_engine` pasan a delegar en `resolve()`.

## Escrituras (Fase 1)

| Punto de escritura | Hoy | Nuevo |
|---|---|---|
| `POST /api/brand/upload` (`main.py:417`) | `UPLOAD_DIR/<filename>` | `brand_sources_dir(brand_id)` (si no hay brand aún: `private/brands/_unassigned/sources`) |
| Assets extraídos en ingesta (`ingestion`/`register_asset`) | `upload_dir` plano | `brand_assets_dir(brand_id)` |
| Imágenes IA (`llm_provider.py:1028`) | `uploads/` | `brand_assets_dir(brand_id)` — la firma de `generate_ai_image` recibe `brand_id` opcional; sin él → `tmp_path()` y `register_asset` lo mueve |
| Logos de marca (`brand_service.py`) | `UPLOAD_DIR` como temp | `tmp_path()` y destino final en `brand_assets_dir` |
| Render PPTX / PDF artístico | `outputs/` y `outputs/artistic_pdf/` | `job_dir(job_id)` |
| Conversión LibreOffice y temps | junto a la fuente | `tmp_path()` |

`BrandAsset.local_path` y `GenerationJob.pptx_path` pasan a guardar **ruta
absoluta o relativa a backend/ consistente** (decisión: relativa a `backend/`,
portable entre host y contenedor `/app`).

## Montajes y URLs

- `app.mount("/files", CORSStaticFiles(directory=PUBLIC_ROOT))` — nuevo.
- `/uploads` se mantiene (legacy) durante la transición; `/outputs` se mantiene
  para los downloads históricos. **`private/` no se monta nunca.**
- `public_url()` centraliza la URL que el backend entrega al frontend; el
  endpoint de librería de imágenes la usa (assets nuevos → `/files/...`,
  legacy → `/uploads/...`). El frontend no cambia lógica: consume la URL que
  llega.
- DELETE de portfolios: si existe `job_dir(job_id)`, se elimina la carpeta
  completa (`shutil.rmtree` tolerante) además del `pptx_path` actual.

## Migración (Fase 2 — data alignment)

`file_reorganization_v1` en `ALIGNMENT_REGISTRY`:

1. **BrandAsset**: por cada fila, `resolve(local_path)` → si está bajo legacy,
   mover a `brand_assets_dir(brand_id)` (assets `is_public` sin brand →
   `brands/_public/assets`), actualizar `local_path`, commit por lote (50).
   Colisión de basename en destino → renombrar con sufijo `_dup{id}` y reportar.
2. **GenerationJob.pptx_path**: mover a `job_dir(job_id)`, actualizar fila.
3. **Brand.logo_path**: ídem hacia `brand_assets_dir`.
4. **Huérfanos** (archivos en legacy sin fila en BD): NO se mueven; se listan
   en el `detail` (truncado) para decisión humana.
5. Resumen `{moved, skipped, orphans, conflicts, failed}`.

Idempotencia: las filas ya apuntando bajo `storage/` se saltan; mover archivo
inexistente = skip reportado. Interrupción → `failed` → reintento al siguiente
arranque (los movidos no se repiten porque la BD ya está actualizada).

## Housekeeping

Al arrancar (junto al dispatch de alineaciones, mismo try/except): vaciar
`storage/tmp/` con antigüedad > 24h (no vaciar todo: un worker puede tener un
temp en uso durante un deploy).

## DevOps

- `docker-compose.yml`: el bind `./backend:/app` ya persiste `storage/` en el
  host (verificado). Añadir línea explícita `./backend/storage:/app/storage`
  en `backend` y `celery-worker` por claridad y paridad con `uploads`.
- `.gitignore`: añadir `storage/`.
- Sin cambios en `ci_cd.yml` (mismo razonamiento de iteraciones previas).

## Restricciones (no negociables)

- Fase 0 NO cambia comportamiento: mismo árbol físico, solo centralización.
  Se mergea/valida antes de activar escrituras nuevas si se quiere por etapas.
- Ningún archivo bajo `private/` accesible por HTTP (test explícito).
- La alineación de migración cumple el contrato de idempotencia del registry.
- `resolve()` es síncrono y barato (sin LLM, sin red); el glob del paso 3 se
  permite porque el árbol por marca es pequeño; si crece, se optimiza con
  lookup en BD por basename.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Migrar 226 archivos con BD desincronizada deja imágenes rotas | Fase 2 actualiza BD y archivo en el mismo lote; fallback de lectura legacy permanece hasta Fase 3 |
| URLs de imágenes cacheadas por el frontend apuntando a legacy | `/uploads` sigue montado durante la transición |
| Render de jobs históricos tras la migración | `resolve()` por basename cubre los JSON históricos; test de integración explícito |
| Deploy en EC2 a mitad de migración | Alineación reanudable; bind mount persiste el progreso |
