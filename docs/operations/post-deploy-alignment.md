# Post-Deploy Alignment Registry

Registro de alineaciones por release. Desde la iteración **Alineaciones de
Datos** (2026-06-11), las TRES capas convergen automáticamente al arrancar el
backend nuevo:

| Capa | Mecanismo | Dónde |
|---|---|---|
| Esquema | ALTERs idempotentes | `database.py` (in-place migrations) |
| Configuración | Seeds (claves nuevas) | `utils/seed.py` |
| **Datos** | **Alineaciones automáticas** (encoladas a Celery al arrancar) | `services/core/data_alignment_service.py` |

**Cómo registrar una alineación de datos nueva**: añadir una función idempotente
al `ALIGNMENT_REGISTRY` con nombre versionado (`_v1`, `_v2`...). El arranque la
detecta, la encola y registra su estado en la tabla `data_alignments`
(`pending/running/done/failed`; los `failed` se reintentan en el siguiente
arranque). Contrato completo en el docstring del módulo.

**Apagado de emergencia**: `system_configs.auto_data_alignment_enabled = "false"`
— el arranque solo loggea las pendientes sin ejecutarlas (útil si una alineación
consume tokens LLM y se quiere controlar el momento).

**Verificación post-deploy**:
```sql
SELECT name, status, detail, finished_at FROM data_alignments ORDER BY id;
```

Este documento queda como **registro de auditoría por release** y como guía
cuando el guard esté apagado (ejecución manual con los scripts de `utils/`).

---

## Iteración 7 — Autenticación, Roles Multi-Usuario y Base Multi-Tenant (2026-07-05)

**Sin comandos manuales.** Alineación automática al arrancar:
- Tablas nuevas `tenants` y `users` → creadas por `Base.metadata.create_all()` (tablas nuevas, no requieren ALTER).
- Columna `brands.tenant_id` (nullable) → auto-ALTER genérico vía `reconcile_additive_columns()` en `database.py`.
- Alineación `tenant_backfill_v1` — crea un `Tenant` "{brand.name} (legacy)" por cada `Brand` existente con `tenant_id IS NULL` y lo asigna. **No consume tokens LLM**, kill switch no necesario.

**Atención post-deploy**:
- Verificar `SELECT name, status, detail FROM data_alignments WHERE name='tenant_backfill_v1';` — el `detail` reporta `{tenants_created, brands_assigned, failed}`.
- `brands.tenant_id` queda **nullable** intencionalmente en esta iteración — no se enforcea `NOT NULL` hasta un release posterior, para evitar una carrera entre la alineación y tráfico de rutas ya scopeadas por tenant (ver `docs/designs/autenticacion-multitenant-design.md` §2.3).
- El scoping por tenant en las rutas de la API todavía no está activo en esta tarea (B1) — llega en B6-B8 del desglose (`docs/tasks/autenticacion-multiusuario-multitenant.md`). Hasta entonces, `tenant_id` existe en el esquema pero no se usa para filtrar.

**Comando manual ejecutado (D1 parcial, 2026-07-06)**: `JWT_SECRET_KEY` es una variable obligatoria nueva (el backend no arranca sin ella) y **no** se resuelve por alineación automática — vive únicamente en el `.env` físico de EC2 (`/home/ubuntu/GuepardAI/.env`, gitignored). Se generó con `openssl rand -hex 32` y se agregó manualmente por SSH (backup previo `.env.bak.<timestamp>` en el mismo directorio), seguido de `docker compose up -d --no-deps backend celery_worker` para recrear ambos contenedores. Verificado: `docker exec guepard-backend printenv | grep JWT_SECRET_KEY` y `GET /docs` → 200.
**Pendiente**: `SUPERADMIN_EMAIL`/`SUPERADMIN_PASSWORD` (env vars) y `utils/seed_superadmin.py` no existen aún — sin ese script, ningún usuario puede loguearse en producción una vez que el login (F1-F4) esté deployado. Debe resolverse antes de D2.

---

## Iteración 6 — Calidad de Selección de Imágenes v2 (2026-06-11)

**Sin comandos manuales.** Alineación automática al arrancar:
- Columna `brand_assets.perceptual_hash` + índice → ALTERs idempotentes en `database.py`.
- Clave `degraded_min_resolution_px` = `"600"` → insertada por `seed.py`.
- Alineación `perceptual_hash_backfill_v1` — calcula el dHash de todos los
  assets existentes (`perceptual_hash IS NULL`). **No consume tokens LLM**
  (puro PIL), por lo que el kill switch no es necesario para esta alineación.

**Atención post-deploy**:
- Verificar `SELECT name, status, detail FROM data_alignments WHERE name='perceptual_hash_backfill_v1';`
  — el `detail` reporta `{processed, failed, missing}`; `missing` = filas cuyo
  archivo físico no se resolvió (mismos huérfanos de `file_reorganization_v1`).
- Hasta que el backfill termine, la no-repetición por gemelos visuales y la
  regla QA `DUPLICATE_IMAGE_ACROSS_SLIDES` solo operan sobre hashes no nulos
  (degradan con gracia, sin error).

---

## Iteración 5 — Reorganización de Storage (2026-06-11)

**Sin comandos manuales.** Alineación automática al arrancar:
- Árbol `storage/` (public/private/tmp) → creado por el servicio al primer uso;
  montado en compose (`./backend/storage:/app/storage`).
- Migración del histórico → alineación `file_reorganization_v1` (mueve archivos
  de uploads/outputs a la jerarquía y actualiza rutas en BD; idempotente).
- Housekeeping de `storage/tmp/` (>24h) en cada arranque.

**Atención post-deploy**:
- Verificar `SELECT name, status, detail FROM data_alignments WHERE name='file_reorganization_v1';`
  — el `detail` reporta `orphans`: archivos en `uploads/` sin fila en BD que NO
  se movieron (decisión humana: borrar o re-ingestar).
- El árbol legacy `uploads/`/`outputs/` queda como fallback de lectura hasta la
  Fase 3 (iteración futura); no borrar manualmente hasta entonces.

---

## Iteración 4 — Gestión de Portfolios (2026-06-11)

**Sin comandos manuales.** Alineación automática al arrancar:
- Columna `generation_jobs.display_name` → ALTER idempotente en `database.py`.
- Sin claves de config ni alineaciones de datos nuevas.

Verificación opcional: `GET /api/library/portfolios?page=1&page_size=5` devuelve
el envelope `{items, total, page, page_size}` ordenado por fecha descendente.

---

## Iteración 3 — Alineaciones de Datos (2026-06-11)

**Sin comandos manuales.** El propio mecanismo se auto-instala:
- Tabla `data_alignments` → creada por `create_all` al arrancar.
- Clave `auto_data_alignment_enabled` = `"true"` → insertada por `seed.py`.
- Primera alineación registrada: `visual_profile_backfill_v1` — **resuelve
  automáticamente el backfill pendiente de la Iteración 1 en EC2** (perfila
  todos los assets con `visual_profile IS NULL`, todas las marcas, idempotente).

---

## Iteración 2 — Fixes de Resiliencia del Pipeline (2026-06-10)

**Sin comandos manuales.** Todo se alinea automáticamente al arrancar:
- Columna `generation_jobs.qa_forced` → ALTER idempotente en `database.py`.
- Clave `qa_feedback_max_chars` → insertada por `seed.py`.

Verificación opcional: `SELECT qa_forced FROM generation_jobs ORDER BY id DESC LIMIT 5;`

---

## Iteración 1 — Selección de Imágenes (2026-06-10)

**Automático al desplegar**: columna `brand_assets.visual_profile` (ALTER),
claves `prompt_classifier_v2`, `prompt_art_director_v2`, `aspect_ratio_tolerance` (seeds).

**Acción manual histórica** (backfill de perfiles): ⚠️ **cubierta por
`visual_profile_backfill_v1` desde la Iteración 3** — ya no requiere ejecución
manual. El script sigue disponible para uso puntual:

```bash
docker exec -it guepard-backend python utils/backfill_visual_profiles.py --brand-id <id>   # una marca
docker exec -it guepard-backend python utils/backfill_visual_profiles.py --all             # todas
docker exec -it guepard-backend python utils/backfill_visual_profiles.py --all --force     # regenerar todo
```

Notas vigentes: idempotente (solo procesa `visual_profile IS NULL`); 1 llamada
Vision por asset; un 429 no aborta el lote; el backend nuevo debe haber
arrancado al menos una vez antes (siembra `prompt_classifier_v2` — sin esa
clave los perfiles quedan NULL sin error). Verificación:
`SELECT count(*) FROM brand_assets WHERE visual_profile IS NOT NULL AND category != 'noise';`
