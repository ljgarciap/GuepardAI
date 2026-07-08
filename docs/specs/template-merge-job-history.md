# Spec: Histórico persistente de Template Merge (listado, búsqueda, renombrado y eliminación)

**Date**: 2026-07-06
**Requested by**: Luis
**Status**: Done — aprobado por Senior Reviewer (`docs/reviews/template-merge-job-history.md`) y QA (`docs/qa/template-merge-job-history-2026-07-07.md`) el 2026-07-07
**Project**: GuepardAI

## Problem

La pestaña Template Merge solo muestra un bloque **"THIS SESSION"** (`completedJobs`
en `template-merge.component.ts:57`) que se llena en memoria mientras el job que
el usuario acaba de lanzar termina de procesarse. No existe ningún
`GET /api/template-merge/jobs` (listado) en el backend — solo `POST /jobs`
(crear), `GET /jobs/{id}` (status de uno) y `GET /jobs/{id}/download`
(main.py:1115, 1166, 1192). Al recargar la página, o al volver en otra sesión,
`completedJobs` se resetea a `[]` y el usuario pierde acceso a presentaciones
que sí siguen existiendo en `template_merge_jobs` y en disco — no hay forma de
recuperarlas sin conocer el `job_id` de memoria.

El Generador (Synthesis Studio) ya resuelve este mismo problema para
`GenerationJob` vía Asset Library → **Portfolios** (`/api/library/portfolios`,
ver `docs/specs/gestion-portfolios.md`). Template Merge quedó fuera de ese
trabajo porque en ese momento el feature ni existía en producción.

## Solution summary

Agregar un histórico persistente de Template Merge con paridad funcional
completa respecto a Portfolios: listado paginado ordenado por fecha
descendente, búsqueda por nombre, filtro por rango de fechas, renombrado de
la etiqueta visible y eliminación con confirmación — reutilizando el mismo
patrón de `GenerationJob`/`/api/library/portfolios` pero sobre
`TemplateMergeJob`. En la UI, el histórico vive en una **pestaña/sección
nueva dentro de la propia página Template Merge**, separada de "THIS
SESSION" (que se mantiene tal cual, para el feedback en vivo de jobs recién
lanzados en la sesión actual).

## Users and roles

- Mismos roles y reglas de `auth-multitenant`
  (`docs/specs/autenticacion-multiusuario-multitenant.md`): `superadmin`,
  `admin`, `cliente`.
- `superadmin` ve todos los jobs de Template Merge, de cualquier tenant.
- `admin`/`cliente` solo ven jobs cuyo `brand_id` pertenezca a su propio
  tenant — mismo criterio que ya aplican `check_job_tenant_access` y
  `tenant_brand_ids_filter` (`auth/dependencies.py`), reutilizados sin
  modificarlos.
- Un job con `brand_id IS NULL` (posible hoy: `TemplateMergeRequest.brand_id`
  es opcional, main.py:1126) sigue el mismo comportamiento ya vigente para
  `GenerationJob`: invisible/no accesible para `admin`/`cliente`, visible
  solo para `superadmin`. No es una regla nueva de este spec.

## Acceptance criteria

**Listado y orden**
- [x] `GET /api/template-merge/jobs` devuelve un envelope
      `{items, total, page, page_size}`, ordenado por `created_at`
      descendente (más reciente primero).
- [x] Por defecto lista jobs en estado `completed`. Un parámetro explícito
      (a decidir con el Architect, ver Open questions) permite incluir
      también `error`. — **Decisión tomada**: sin parámetro de estado en
      esta iteración (ver Open questions); `error` queda fuera de alcance.
- [x] Respeta tenant scoping: `admin`/`cliente` solo ven jobs de brands de
      su tenant; `superadmin` ve todos.
- [x] Parámetro opcional `brand_id`: si se pasa, valida con
      `check_brand_tenant_access` y filtra a ese brand.

**Paginación**
- [x] Parámetros `page` (default 1, mínimo 1) y `page_size` (default 12,
      máximo 100). `total` refleja el conteo con filtros aplicados.
- [x] `page` fuera de rango devuelve `items: []` con el `total` correcto
      (no error).
- [x] El frontend muestra paginador (anterior/siguiente + página
      actual/total) solo cuando hay más de una página.

**Búsqueda**
- [x] Parámetro `search`: coincidencia parcial case-insensitive contra el
      nombre visible (`display_name` si existe, o el basename de
      `output_path`).
- [x] Parámetros `date_from` y `date_to` (ISO `YYYY-MM-DD`, inclusivos,
      combinables entre sí y con `search`). `date_from > date_to` → 422.
- [x] El frontend tiene cuadro de búsqueda con debounce (~300 ms) y dos
      selectores de fecha; cambiar cualquier filtro resetea a página 1.
- [x] Sin resultados → mensaje de estado vacío claro (no tabla en blanco).

**Renombrado**
- [x] `PATCH /api/template-merge/jobs/{job_id}` con `{display_name}`: trim,
      no vacío, máximo 120 caracteres; 422 si inválido, 404 si no existe o
      no es accesible para el tenant del usuario (vía
      `check_job_tenant_access`).
- [x] El renombrado NO toca el archivo físico ni la URL de descarga.
- [x] El frontend permite renombrar desde el listado (edición inline o modal
      pequeño) y refleja el cambio sin recargar la página completa.

**Eliminación**
- [x] `DELETE /api/template-merge/jobs/{job_id}`: elimina el registro y el
      archivo físico en `output_path` (tolerante: si el archivo no existe,
      el borrado en BD procede igual).
- [x] Solo se pueden eliminar jobs en estado terminal (`completed` o
      `error`); un job en `pending`/`processing` devuelve 409 (evita que el
      pipeline Celery escriba sobre un job borrado).
- [x] 404 si el job no existe o no pertenece al tenant del usuario; repetir
      el DELETE de un job ya borrado → 404 (idempotencia práctica).
- [x] El frontend muestra **modal de confirmación** con el nombre visible
      del job antes de borrar; cancelar no produce ninguna llamada.
- [x] Tras confirmar, el ítem desaparece del listado y el `total` se
      actualiza.

**Frontend — integración con la página existente**
- [x] Nueva pestaña/sección "History" (o equivalente) dentro de
      `template-merge.component.*`, separada de "THIS SESSION".
- [x] "THIS SESSION" no cambia de comportamiento — sigue siendo el feedback
      en vivo de jobs lanzados en la sesión actual del navegador.
- [x] Al completarse un job en "THIS SESSION", el histórico persistente lo
      refleja sin necesidad de recargar manualmente (ya sea por refresco
      automático de la lista o invalidación explícita al completar).
- [x] La descarga desde el histórico reutiliza el patrón ya corregido de
      fetch-a-blob autenticado (`triggerBlobDownload`,
      `frontend/src/app/utils/download.util.ts`) — no un `<a href download>`
      ni `window.open` directos, que no llevan el header `Authorization`.

**Transversal**
- [x] Tests backend (pytest) para orden, filtros, paginación, tenant
      scoping, validaciones de rename y limpieza completa del delete.
- [x] Tests frontend (Karma) para el servicio y la lógica del componente
      (filtros → reset de página, modal → confirmación/cancelación).
- [x] Suites backend y frontend completas en verde.

## Edge cases and error scenarios

- **`display_name` con solo espacios** → 422 (trim primero).
- **`search` con caracteres especiales de LIKE** (`%`, `_`) → escapados (no
  actúan como comodines), mismo helper `_escape_like` ya usado en
  `list_library_portfolios`.
- **Borrar mientras se descarga** → el download de un job borrado devuelve
  404 (comportamiento ya existente del endpoint de descarga).
- **Archivo físico ya ausente** → el DELETE procede y reporta éxito.
- **Job con `brand_id IS NULL`** → invisible para `admin`/`cliente`, visible
  solo para `superadmin` (comportamiento heredado, no nuevo — ver "Users and
  roles").
- **Dos pestañas abiertas, una borra y la otra renombra el mismo job** → la
  segunda recibe 404 y el frontend refresca el listado.
- **Rango de fechas en el límite** → `date_to` incluye todo el día (hasta
  23:59:59), no solo la medianoche.
- **`template_asset_id` referenciaba un `BrandAsset` que luego fue borrado**
  → el listado no depende del asset original (usa `output_path`/
  `display_name` del job), así que no debe romperse; confirmar en
  implementación que no hay `join` obligatorio contra `brand_assets`.

## Out of scope

- Soft-delete / papelera de reciclaje (el borrado es definitivo, igual que
  en Portfolios).
- Renombrar el archivo físico en disco o la URL de descarga.
- Cambiar el criterio de tenant-scoping para jobs con `brand_id IS NULL`
  (eso es territorio de `auth-multitenant`, ya cerrado).
- Unificar este histórico con el de Portfolios en una sola vista (decisión
  tomada con Luis: quedan como secciones separadas dentro de cada página).
- Migrar el `TemplateMergeJob` histórico existente (jobs ya completados
  antes de este feature) — deben aparecer automáticamente en el listado sin
  ningún backfill, porque el modelo ya tiene todas las columnas necesarias
  (`display_name`, `created_at`, `status`, `output_path`); no se requiere
  alineación de datos.

## Open questions

- [Architect] ¿El listado debe incluir jobs en `error` por defecto (para que
  el usuario vea qué falló) o solo bajo un filtro explícito de estado? En
  Portfolios (`GenerationJob`) el listado solo incluye `completed`.
- [Architect] Refresco del histórico al completarse un job de "THIS
  SESSION": ¿polling propio de la pestaña History, invalidación explícita
  desde el callback de "THIS SESSION", o simplemente recargar al cambiar de
  pestaña? Impacta el diseño del componente.
- [Frontend] ¿El histórico comparte el `BrandService` (agregando métodos
  `getTemplateMergeJobs`/`renameTemplateMergeJob`/`deleteTemplateMergeJob`,
  igual patrón que `getLibraryPortfolios`) o vive en un servicio propio de
  Template Merge? `template-merge.component.ts` hoy inyecta `HttpClient`
  directo, no `BrandService`.

## References

- API docs: `docs/api/template-merge.md` (documenta los 3 endpoints nuevos y el flujo completo de Template Merge).
- Backend: `main.py:1115` (`create_template_merge_job`), `main.py:1166`
  (`get_template_merge_job_status`), `main.py:1192`
  (`download_template_merge_result`) — endpoints existentes a extender con
  list/rename/delete. `models.py:493` (`TemplateMergeJob`).
  `auth/dependencies.py` (`check_job_tenant_access`,
  `tenant_brand_ids_filter`, `check_brand_tenant_access` — reutilizar, no
  reimplementar).
- Spec análoga (mismo patrón, otro modelo): `docs/specs/gestion-portfolios.md`.
- Frontend: `frontend/src/app/pages/template-merge/template-merge.component.*`
  (sección "THIS SESSION" actual), `frontend/src/app/utils/download.util.ts`
  (`triggerBlobDownload`, patrón de descarga autenticada a reutilizar).
- Spec relacionada: `docs/specs/autenticacion-multiusuario-multitenant.md`
  (reglas de tenant scoping que este feature hereda sin modificar).
