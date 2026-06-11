# Spec: Reorganización Jerárquica del Storage de Archivos

**Date**: 2026-06-11
**Requested by**: Luis
**Status**: Draft — pendiente aprobación para implementar
**Project**: GuepardAI

## Problem

Todos los archivos del sistema conviven en dos carpetas planas:

- **`uploads/` (226 archivos, 78.7 MB)**: documentos fuente subidos (pptx/pdf,
  incluyendo informes corporativos del knowledge), 222 assets de imagen
  extraídos de TODAS las marcas mezclados, imágenes generadas por IA y archivos
  temporales de `brand_service`.
- **`outputs/` (23 archivos, 453.6 MB)**: presentaciones finales planas por job,
  sin retención posible.

Consecuencias medidas:
1. **Resolución de rutas dispersa**: ~15 puntos del código reconstruyen rutas a
   mano probando `uploads/<basename>` → `backend/uploads/<basename>`
   (`pptx_renderer.py` ×6, `painter.py`, `layout_engine.py`,
   `vision_layout_engine.py`, `painter_bridge.py`, `artistic_pdf_service.py` ×2,
   `art_director_service._resolve_asset_dims`, `backfill_visual_profiles`,
   `asset_engine`, `llm_provider`). La BD agrava: `local_path` guarda a veces
   ruta relativa, a veces solo basename.
2. **Seguridad**: `/uploads` y `/outputs` se montan como estáticos públicos
   (`main.py:96-97`) — los documentos fuente subidos son descargables por URL.
3. **Sin soberanía por marca**: borrar una marca no puede limpiar sus archivos.
4. **Colisiones por basename**: todo el sistema asume nombres únicos globales.

## Solution summary

Tres fases. **Fase 0**: un `StorageService` centralizado que se convierte en el
único punto que sabe dónde viven los archivos (reemplaza los ~15 sitios de
resolución manual, sin mover nada aún). **Fase 1**: jerarquía nueva con
separación public/private para las escrituras nuevas, con fallback de lectura
al legacy; los montajes estáticos dejan de exponer los documentos fuente.
**Fase 2**: migración del histórico como alineación de datos
(`file_reorganization_v1`) — mover archivos + actualizar rutas en BD,
idempotente, ejecutada automáticamente post-deploy por el mecanismo de la
iteración anterior.

Jerarquía objetivo:

```
backend/storage/
  public/                      # único árbol montado como estático
    brands/{brand_id}/assets/  # assets extraídos + generados por IA
    jobs/{job_id}/             # outputs finales del job (pptx/pdf)
  private/
    brands/{brand_id}/sources/ # documentos subidos — NUNCA servidos
  tmp/                         # intermedios (conversiones, temps) — limpiable
```

## Users and roles

- **Pipelines de ingesta y generación**: escriben/leen vía StorageService.
- **Frontend**: sigue mostrando imágenes y descargando presentaciones — las
  URLs de assets nuevos cambian de `/uploads/...` a `/files/...`; las legacy
  siguen funcionando durante la transición.
- **Operador**: gana borrado por marca/job y un árbol privado para fuentes.
- Sin cambios de permisos de usuario.

## Acceptance criteria

**Fase 0 — StorageService (sin cambio de comportamiento)**
- [ ] Existe `services/core/storage_service.py` con API única: `resolve(ref)`
      (acepta ruta absoluta, relativa legacy o basename y devuelve ruta
      existente o None), `save_source(brand_id, filename, content)`,
      `asset_dir(brand_id)`, `job_dir(job_id)`, `tmp_path(suffix)`.
- [ ] Los ~15 sitios de resolución manual usan `resolve()`; no queda ningún
      `os.path.join("uploads", ...)` de lectura fuera del servicio (grep como
      criterio verificable; se permiten en el propio servicio y en tests).
- [ ] Suites backend y frontend completas en verde sin cambios de assets.

**Fase 1 — Jerarquía para escrituras nuevas**
- [ ] Documentos subidos → `private/brands/{id}/sources/`; assets extraídos y
      de IA → `public/brands/{id}/assets/`; outputs de render →
      `public/jobs/{job_id}/`; temporales → `tmp/`.
- [ ] `resolve()` encuentra archivos en la jerarquía nueva Y en el legacy
      (nuevo primero); una generación con assets mezclados (viejos en
      `uploads/`, nuevos en `storage/`) renderiza correctamente.
- [ ] Montaje estático nuevo `/files` → `storage/public`. `/uploads` legacy se
      mantiene durante la transición. **Ningún archivo de
      `private/` es accesible por HTTP** (criterio de seguridad verificable).
- [ ] El endpoint de librería de imágenes devuelve URL servible correcta para
      assets en cualquiera de las dos ubicaciones.
- [ ] El DELETE de portfolios elimina la carpeta `public/jobs/{job_id}/`
      completa cuando existe (además del comportamiento actual).
- [ ] `storage/` añadido a `.gitignore` y `tmp/` se vacía al arrancar el
      backend (housekeeping, tolerante a fallos).

**Fase 2 — Migración del histórico**
- [ ] Alineación `file_reorganization_v1` registrada: mueve los archivos de
      `uploads/`/`outputs/` a la jerarquía y actualiza `BrandAsset.local_path`,
      `GenerationJob.pptx_path` y `Brand.logo_path` en BD. Por lotes,
      idempotente (re-ejecutar converge a 0), un fallo individual no aborta.
- [ ] Assets sin marca identificable o archivos huérfanos (sin fila en BD) se
      reportan en el detail sin moverse (decisión humana posterior).
- [ ] Tras la migración, una generación completa usa solo rutas nuevas.

**Transversal**
- [ ] Tests: unit del StorageService (resolve en ambas ubicaciones, basename,
      ausente), integración del render con archivo movido, y de la alineación
      con archivos reales en tmp de test.
- [ ] Suite completa en verde.

## Edge cases and error scenarios

- **Mismo basename en dos marcas** (legacy permite colisión): `resolve()` con
  contexto de marca prioriza `brands/{id}/assets/`; la migración detecta la
  colisión al mover y registra el conflicto sin sobrescribir.
- **Archivo referenciado en BD pero ausente en disco** → `resolve()` devuelve
  None y el caller mantiene su manejo actual (placeholder/skip).
- **Migración interrumpida a mitad** (deploy/reinicio) → estado `failed`,
  reintento automático en el siguiente arranque; los ya movidos no se re-mueven
  (la BD ya apunta a la ruta nueva).
- **Job sin job_dir** (generados pre-migración ya movidos a `jobs/{id}/`) →
  `pptx_path` actualizado por la migración; el download endpoint usa la BD, no
  convenciones.
- **planning_json/render_elements históricos con basenames** → cubiertos por
  `resolve()` (busca por basename en árbol nuevo y legacy); los jobs completados
  no se re-renderizan, así que no se reescriben esos JSON.
- **Disco lleno al migrar** → fallo del lote reportado; idempotencia permite
  reanudar tras liberar espacio.
- **EC2: bind mount `./backend:/app`** ya persiste `storage/` en el host;
  `git reset --hard` del deploy no toca directorios no rastreados (gitignored).

## Out of scope

- **Fase 3** (retirar el fallback legacy y desmontar `/uploads`): iteración
  posterior, cuando la migración lleve estable un ciclo.
- Políticas de retención automáticas de outputs (la jerarquía las habilita).
- Almacenamiento externo (S3/CDN).
- Mover `templates/`, `custom_fonts/` o `placeholder` assets del sistema.
- Limpieza de huérfanos detectados (solo se reportan).

## Open questions

- Ninguna bloqueante. Decisiones con el Arquitecto: separación `public/private`
  en la raíz del árbol (hace el montaje estático trivial y elimina el riesgo de
  fuga por construcción); migración como data alignment (reutiliza el mecanismo
  de la iteración anterior, ya desplegado).

## References

- Evidencia del análisis: conversación Arquitecto 2026-06-11 (conteo de sitios
  de resolución, inventario uploads/outputs, montajes estáticos).
- `services/core/data_alignment_service.py` — mecanismo para la Fase 2.
- `docker-compose.yml:39-42` — bind mounts existentes (cubren `storage/`).
- `main.py:92-97` — definición actual de UPLOAD_DIR/OUTPUT_DIR y montajes.
