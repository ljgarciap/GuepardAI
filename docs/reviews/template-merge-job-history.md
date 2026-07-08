# Review: Histórico persistente de Template Merge

**Date**: 2026-07-07
**Reviewer**: Senior Reviewer
**Scope**: `backend/main.py` (3 endpoints nuevos), `backend/tests/test_template_merge_history.py`, `frontend/src/app/services/brand.service.ts` (+specs), `frontend/src/app/pages/template-merge/*` (component + html + css + specs), `frontend/src/app/pages/generator/*`, `frontend/src/app/pages/asset-library/*`, `frontend/src/app/utils/download.util.ts` (fix de descarga autenticada, mismo PR), `docs/api/template-merge.md`, manuales de usuario (`admin.md`, `cliente.md`, `superadmin.md`)
**Spec**: `docs/specs/template-merge-job-history.md`
**Design**: `docs/designs/template-merge-job-history.md`
**Tests**: 442 passed, 1 skipped (backend); 60/60 (Karma) — verificado corriendo ambas suites completas, no solo confiado en el reporte del dev.

**Veredicto: 🟢 Aprobado para QA.** Implementación fiel al diseño, sin desvíos de arquitectura, sin bugs de seguridad ni de lógica encontrados. Dos hallazgos 🟡 no bloqueantes, quedan como fast-follow.

---

## Verificación contra el diseño

- Los 3 endpoints (`GET/PATCH/DELETE /api/template-merge/jobs...`) replican exactamente el patrón ya aprobado de `list_library_portfolios`/`rename_library_portfolio`/`delete_library_portfolio` — mismo escapado de LIKE (`_escape_like`), misma validación de rango de fechas, mismo tenant scoping (`check_brand_tenant_access`/`check_job_tenant_access`/`tenant_brand_ids_filter`) reutilizado sin reimplementar.
- Confirmé que `TemplateMergeJob.status` es un `String(30)` plano (no un enum) y que las comparaciones en los 3 endpoints nuevos usan literales `"completed"`/`"error"`, no el enum `GenerationJobStatus` — el riesgo que el propio design doc señaló explícitamente está correctamente evitado.
- `delete_template_merge_job` borra el job y su `output_path` (el archivo generado), **no** el `template_asset_id` (el blueprint subido por el usuario, un `BrandAsset` reutilizable) — correcto, verificado en `test_delete_removes_job_and_physical_file`.
- Frontend: el tab "HISTORY" es una vista separada de "THIS SESSION" (que no cambió comportamiento), con los 3 métodos nuevos en `brand.service.ts` — ninguna llamada HTTP nueva vive suelta en el componente. La descarga desde History reutiliza `downloadJobFile()` (un solo helper privado compartido con `downloadResult()` de la vista de sesión) — no hay lógica de blob duplicada.
- Los manuales de usuario (`admin.md`, `superadmin.md`) tenían la instrucción **incorrecta** que originó esta iteración ("usa Strategic Assets → Portfolios para histórico" — nunca fue cierto para Template Merge). Confirmé que la corrección está en los 3 archivos y no queda ningún rastro del texto viejo (`grep` sobre `docs/manuals/` no encontró coincidencias).

## Seguridad

- Las 3 rutas nuevas tienen `Depends(get_current_user)` + scoping de tenant — ninguna queda abierta.
- `search` va por `.ilike()` parametrizado de SQLAlchemy (no concatenación de SQL crudo); comodines de usuario escapados antes de interpolar en el patrón. Sin inyección.
- Verifiqué el orden de operaciones en `rename_template_merge_job`/`delete_template_merge_job`: `check_job_tenant_access` corre antes de tocar cualquier atributo del `job`, así que un `job_id` inexistente nunca llega a `job.status`/`job.display_name` con `job=None` (la función de chequeo trata `None` como 404 explícitamente).

## 🟡 Suggestions (no bloqueantes)

### 1. Los 3 endpoints nuevos viven en `main.py`, no en `backend/routers/template_merge.py`

`CLAUDE.md` dice explícitamente: *"New routes go in `backend/routers/`... this is the pattern going forward; `main.py` stays legacy-only"*, y el propio anti-pattern table lo marca como algo a atrapar en review. Los 3 endpoints nuevos son código nuevo, no un retrofit — técnicamente califican.

Decidí (como Architect) mantenerlos junto a los otros 5 endpoints de Template Merge que ya viven en `main.py`, por consistencia con el precedente más reciente: `docs/designs/gestion-portfolios.md` (2026-06-11) hizo exactamente lo mismo para Portfolios (endpoints nuevos agregados a `main.py`, no a `routers/`), y fue aprobado sin objeción. Partir solo 3 de los 8 endpoints de Template Merge a `routers/` mientras los otros 5 quedan en `main.py` habría creado un split-brain peor que la deuda actual.

**Recomendación**: no bloquear esta entrega por esto, pero registrar como tarea de housekeeping separada: migrar los dominios legacy completos (`generation`, `library`, `template-merge`) a `routers/` de una sola vez, no endpoint por endpoint.

### 2. El histórico no lista merges con `status="error"`

Documentado como decisión explícita del Architect en el spec (Open questions) — un usuario cuyo merge falló no tiene forma de verlo en History (ni en "THIS SESSION" tras recargar). Es el mismo comportamiento que Portfolios ya tiene para `GenerationJob`, así que no es una regresión, pero vale la pena que Luis confirme si esto es aceptable a mediano plazo o si amerita un parámetro de filtro por estado.

## Nota de entorno (no es código, no bloquea)

Durante la verificación encontré que `backend/.env.test` apunta a `host.docker.internal:5433`, que no resuelve a un puerto alcanzable al correr `pytest` directo en el host de Windows (fuera de un contenedor) — el intento de conexión tarda ~4 minutos en expirar y termina saltando (`skip`) los 442 tests silenciosamente en vez de fallar ruidosamente. Tuve que apuntar temporalmente a `localhost:5433` para poder verificar, y revertí el archivo antes de terminar. No es parte de este feature, pero cualquiera que corra tests localmente (fuera de un devcontainer) va a pisar la misma piedra sin ningún mensaje de error claro — vale la pena que DevOps lo revise.
