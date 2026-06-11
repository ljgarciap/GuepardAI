# Design: Gestión de Portfolios

**Date**: 2026-06-11
**Architect**: aprobado
**Spec**: `docs/specs/gestion-portfolios.md`
**Status**: Approved — listo para desglose del PM
**Rama**: `feature/data-alignments` (rama de iteración activa)

## Backend

### Modelo (`models.py` + `database.py`)
- `GenerationJob.display_name = Column(String(120), nullable=True)`.
- ALTER idempotente en el bloque de in-place migrations:
  `ALTER TABLE generation_jobs ADD COLUMN IF NOT EXISTS display_name VARCHAR(120);`
- Nombre visible (regla única, helper en `main.py` o servicio):
  `display_name or os.path.basename(pptx_path) or f"Presentation_{id}.pptx"`.

### `GET /api/library/portfolios` (extender el existente, `main.py:500`)
Query params: `brand_id` (existente), `search: str = None`,
`date_from: date = None`, `date_to: date = None`,
`page: int = 1`, `page_size: int = 12`.

- Validaciones: `page >= 1`, `1 <= page_size <= 100`, `date_from <= date_to`
  (422 si no). `date_to` se expande a fin de día (`23:59:59`).
- Filtro search: escapar `%` y `_` del input; aplicar
  `OR(display_name ILIKE %term%, pptx_path ILIKE %term%)` — cubre renombradas
  y no renombradas. Nota: si un job renombrado ya no coincide por su filename,
  es el comportamiento esperado (el nombre visible es el que cuenta para el
  usuario; el OR es por simplicidad y cubre el caso null).
- Orden: `ORDER BY created_at DESC`.
- `total = query.count()` antes de `offset/limit`.
- Respuesta: `{"items": [...], "total": int, "page": int, "page_size": int}`
  — los items conservan los campos actuales + `display_name` ya resuelto.
- El prefetch de feedback existente se mantiene, pero acotado a los job_ids de
  la página (no global como hoy).

### `PATCH /api/library/portfolios/{job_id}` (nuevo)
Body Pydantic: `{display_name: str}`. Trim → no vacío y ≤ 120 chars (422).
404 si no existe. Devuelve el ítem actualizado con el nombre resuelto.

### `DELETE /api/library/portfolios/{job_id}` (nuevo)
1. 404 si no existe; 409 si `status` no es terminal (`COMPLETED`/`ERROR`).
2. Borrado explícito de dependencias sin cascade, en orden:
   `GenerationJobFeedback` → `ArtDirectorDecision` → archivo físico
   (`os.remove` en try/except tolerante) → `db.delete(job)` (las slides caen
   por el cascade existente). Una sola transacción para lo de BD.
3. Respuesta: `{"deleted": true, "id": job_id}`.

## Frontend (Angular 19, standalone, sin libs nuevas)

### `brand.service.ts`
- `getLibraryPortfolios(brandId, opts)` → ahora con params de búsqueda/página,
  tipado del envelope `PortfolioPage`.
- `renamePortfolio(jobId, displayName)` → PATCH.
- `deletePortfolio(jobId)` → DELETE.

### `asset-library.component` (pestaña portfolios)
- Estado nuevo: `portfolioSearch`, `portfolioDateFrom/To`, `portfolioPage`,
  `portfolioTotal`. Cambio de cualquier filtro → página 1 + reload.
- Debounce de búsqueda (~300 ms) con `Subject` + `debounceTime` (RxJS ya
  disponible; sin dependencias nuevas).
- Renombrado inline: icono de edición → input con confirmar/cancelar
  (Enter/Escape); optimista no: refrescar el ítem con la respuesta del PATCH.
- Modal de confirmación de borrado: revisar si existe un patrón de modal en la
  app y reutilizarlo; si no, modal simple en el propio componente (overlay +
  card) mostrando el nombre visible. Confirmar → DELETE → reload de la página
  actual (si la página queda vacía y no es la 1, retroceder una página).
- Estado vacío con mensaje cuando `total == 0` con filtros activos.
- CSS en el componente (convención: nada de Tailwind en el frontend Angular).

## Evaluación DevOps (CI/CD) — solicitada por Luis

Revisado `.github/workflows/ci_cd.yml` contra esta feature:

| Aspecto | ¿Requiere cambio en CI? |
|---|---|
| Tests backend nuevos (pytest) | **No** — el job `backend-tests` ejecuta `tests/` completo con la BD pgvector de servicio |
| Tests frontend nuevos (Karma) | **No** — el job `frontend-tests` ejecuta toda la suite (`ng test --watch=false`) y recogerá los specs nuevos automáticamente |
| Columna `display_name` | **No** — ALTER idempotente al arrancar (patrón establecido); el deploy con `docker compose up --build` lo aplica solo |
| Endpoints nuevos | **No** — mismo contenedor backend; Nginx del frontend ya proxya `/api/*` |
| Variables de entorno / secretos | **No** — no se introducen |
| Build del frontend | **No** — el deploy reconstruye la imagen frontend (multi-stage con `ng build`) |

**Conclusión DevOps: cero cambios en `ci_cd.yml`** — la feature viaja completa
con el pipeline actual. Única tarea DevOps: verificación post-deploy (checklist
en el desglose del PM). Si Karma fallara en CI por specs nuevos con
ChromeHeadless, es un fallo de test, no de pipeline.

## Restricciones (no negociables)

- Sin dependencias npm nuevas; RxJS y HttpClient existentes.
- Llamadas HTTP solo desde `brand.service.ts` (nunca `fetch` en componentes).
- El DELETE valida estado terminal — proteger el pipeline Celery es requisito.
- Escapado de comodines LIKE en el search (no inyección de patrones).
- Pydantic para el body del PATCH (no dict crudo).

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Breaking change del envelope rompe otro consumidor del endpoint | Verificado: el único consumidor es `asset-library.component` (grep en frontend); se migra en la misma iteración |
| Borrado accidental (es definitivo) | Modal con nombre explícito + solo estados terminales; papelera queda anotada como mejora futura |
| Karma headless inestable en CI con specs de modal | Specs de lógica (no de DOM profundo); el patrón ya existe en `brand.service.spec.ts` |
