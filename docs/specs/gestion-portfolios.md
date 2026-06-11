# Spec: Gestión de Portfolios (listado, búsqueda, renombrado y eliminación)

**Date**: 2026-06-11
**Requested by**: Luis
**Status**: Done — validado por Luis en prueba manual local (2026-06-11); viaja en el merge de feature/data-alignments junto con Alineaciones de Datos
**Project**: GuepardAI

## Problem

En la pestaña **Portfolios** de Strategic Assets no es fácil encontrar una
presentación generada: el backend devuelve todos los jobs completados sin
ordenar (orden de inserción — las recientes quedan al final), sin búsqueda ni
paginación, y el frontend pinta la lista completa sin controles. El "nombre"
es el nombre del archivo físico (`Presentation_42.pptx`), no editable. No
existe forma de eliminar una presentación que ya no se quiere.

## Solution summary

Convertir la pestaña Portfolios en un listado gestionable: ordenado de la más
reciente a la más antigua, con búsqueda por nombre y rango de fechas,
paginación server-side, renombrado de la presentación (etiqueta visible, sin
tocar el archivo físico) y eliminación con confirmación previa desde un modal.

## Users and roles

- **Usuario de GuepardAI** (única persona/rol actual): gestiona sus
  presentaciones generadas desde la pestaña Portfolios.
- Sin cambios de permisos. El filtro por `brand_id` existente se mantiene.

## Acceptance criteria

**Listado y orden**
- [ ] `GET /api/library/portfolios` devuelve por defecto las presentaciones
      ordenadas por `created_at` descendente (más reciente primero).
- [ ] La respuesta cambia a envelope: `{items, total, page, page_size}`.
      El frontend consume el nuevo formato (no quedan consumidores del array plano).

**Paginación**
- [ ] Parámetros `page` (default 1, mínimo 1) y `page_size` (default 12,
      máximo 100). `total` refleja el conteo con filtros aplicados.
- [ ] `page` fuera de rango devuelve `items: []` con el `total` correcto (no error).
- [ ] El frontend muestra paginador (anterior/siguiente + página actual/total)
      solo cuando hay más de una página.

**Búsqueda**
- [ ] Parámetro `search`: coincidencia parcial case-insensitive contra el
      nombre visible (el `display_name` si existe, o el nombre de archivo).
- [ ] Parámetros `date_from` y `date_to` (ISO `YYYY-MM-DD`, inclusivos,
      combinables entre sí y con `search`). `date_from > date_to` → 422.
- [ ] El frontend tiene cuadro de búsqueda con debounce (~300 ms) y dos
      selectores de fecha; cambiar cualquier filtro resetea a página 1.
- [ ] Sin resultados → mensaje de estado vacío claro (no tabla en blanco).

**Renombrado**
- [ ] Columna nueva `generation_jobs.display_name` (nullable) con ALTER
      idempotente; si es null, el nombre visible es el basename actual
      (compatibilidad total con datos existentes).
- [ ] `PATCH /api/library/portfolios/{job_id}` con `{display_name}`: trim,
      no vacío, máximo 120 caracteres; 422 si inválido, 404 si no existe.
- [ ] El renombrado NO toca el archivo físico ni la URL de descarga.
- [ ] El frontend permite renombrar desde el listado (edición inline o modal
      pequeño) y refleja el cambio sin recargar la página completa.
- [ ] El `search` por nombre encuentra tanto renombradas (por su nuevo nombre)
      como no renombradas (por su nombre de archivo).

**Eliminación**
- [ ] `DELETE /api/library/portfolios/{job_id}`: elimina el job, sus slides
      (cascade existente), su feedback (`GenerationJobFeedback`), sus
      decisiones de arte (`ArtDirectorDecision`) y el archivo físico
      (tolerante: si el archivo no existe, el borrado en BD procede igual).
- [ ] Solo se pueden eliminar jobs en estado terminal (`COMPLETED` o `ERROR`);
      un job en proceso devuelve 409 (evita que el pipeline Celery escriba
      sobre un job borrado).
- [ ] 404 si el job no existe; repetir el DELETE de un job ya borrado → 404
      (idempotencia práctica).
- [ ] El frontend muestra **modal de confirmación** con el nombre visible de
      la presentación antes de borrar; cancelar no produce ninguna llamada.
- [ ] Tras confirmar, el ítem desaparece del listado y el `total` se actualiza.

**Transversal**
- [ ] Tests backend (pytest) para orden, filtros, paginación, validaciones de
      rename y la limpieza completa del delete.
- [ ] Tests frontend (Karma) para el servicio y la lógica del componente
      (filtros → reset de página, modal → confirmación/cancelación).
- [ ] Suites backend y frontend completas en verde.

## Edge cases and error scenarios

- **`display_name` con solo espacios** → 422 (trim primero).
- **`search` con caracteres especiales de LIKE** (`%`, `_`) → escapados (no
  actúan como comodines).
- **Borrar mientras se descarga** → el download de un job borrado devuelve 404
  (comportamiento actual del endpoint de descarga al no encontrar el job).
- **Archivo físico ya ausente** (limpieza manual previa en disco) → el DELETE
  procede y reporta éxito.
- **PDF artístico además del PPTX** → si `pptx_path` apunta al output del job,
  se borra ese archivo; outputs huérfanos de otros formatos quedan fuera de
  alcance (ver Out of scope).
- **Dos pestañas abiertas, una borra y la otra renombra el mismo job** → la
  segunda recibe 404 y el frontend refresca el listado.
- **Rango de fechas en el límite** → `date_to` incluye todo el día (hasta
  23:59:59), no solo la medianoche.

## Out of scope

- Soft-delete / papelera de reciclaje (el borrado es definitivo).
- Renombrar el archivo físico en disco o la URL de descarga.
- Búsqueda full-text sobre el contenido de las slides.
- Limpieza de outputs huérfanos históricos en `backend/outputs/` (tarea de
  housekeeping separada si se necesita).
- Multi-usuario/permisos por rol.

## Open questions

- Ninguna bloqueante. Decisiones tomadas con el Arquitecto: borrado físico
  real (no papelera), `display_name` como etiqueta (el archivo no se renombra),
  paginación server-side desde el inicio, y estados terminales como única
  condición de borrado.

## References

- Backend: `main.py:500` (`list_library_portfolios` — endpoint a extender),
  `models.py` (`GenerationJob`, cascade de slides; `GenerationJobFeedback` y
  `ArtDirectorDecision` sin cascade — limpieza explícita), `database.py`
  (patrón in-place migrations para `display_name`).
- Frontend: `frontend/src/app/pages/asset-library/asset-library.component.*`
  (pestaña `portfolios`), `frontend/src/app/services/brand.service.ts`
  (`getLibraryPortfolios`).
- CI/CD: `.github/workflows/ci_cd.yml` (evaluación DevOps en el design doc).
