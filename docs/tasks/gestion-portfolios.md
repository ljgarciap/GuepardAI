# Tasks: Gestión de Portfolios

**Date**: 2026-06-11
**PM**: desglose del diseño `docs/designs/gestion-portfolios.md`
**Spec**: `docs/specs/gestion-portfolios.md`
**Status**: Ready — pendiente aprobación de Luis para arrancar
**Rama**: `feature/data-alignments`

## Orden de ejecución

```
B1 (listado: orden + filtros + paginación) ─┐
B2 (display_name + PATCH) ──────────────────┼──▶ B4 (tests backend) ─┐
B3 (DELETE + limpieza) ─────────────────────┘                        ├──▶ D1 (verificación DevOps post-merge)
F1 (servicio + listado UI) ──▶ F2 (rename + delete UI) ──▶ F3 (tests frontend) ─┘
T1 (Tech Writer) — en paralelo

Backend y Frontend trabajan EN PARALELO (no comparten archivos).
F1 puede empezar contra el contrato del design doc sin esperar a B1.
```

---

### B1 — Listado: orden, búsqueda, fechas y paginación

**Agent**: Backend Dev · **Depends on**: none · **Estimación**: 3 h

Extender `list_library_portfolios`: `ORDER BY created_at DESC`, params
`search` (ILIKE con escapado de `%`/`_`, sobre display_name OR pptx_path),
`date_from`/`date_to` (inclusivos, fin de día en date_to, 422 si invertidos),
`page`/`page_size` (defaults 1/12, máx 100), envelope
`{items, total, page, page_size}`. Prefetch de feedback acotado a la página.

**Files**: `backend/main.py`
**Acceptance**: criterios de Listado, Paginación y Búsqueda (backend) de la spec.

---

### B2 — Renombrado: columna + PATCH

**Agent**: Backend Dev · **Depends on**: none (paralela a B1; coordinar merge en main.py) · **Estimación**: 2 h

`display_name` en `GenerationJob` + ALTER idempotente en `database.py`;
`PATCH /api/library/portfolios/{job_id}` con body Pydantic (trim, 1-120 chars,
422/404); helper único de nombre visible usado por listado y PATCH.

**Files**: `backend/models.py`, `backend/database.py`, `backend/main.py`
**Acceptance**: criterios de Renombrado (backend) de la spec.

---

### B3 — Eliminación con limpieza completa

**Agent**: Backend Dev · **Depends on**: none (paralela; coordinar merge en main.py) · **Estimación**: 2-3 h

`DELETE /api/library/portfolios/{job_id}`: 404 inexistente, 409 si estado no
terminal, borrado de `GenerationJobFeedback` + `ArtDirectorDecision` +
archivo físico (tolerante) + job (slides por cascade), en una transacción.

**Files**: `backend/main.py`
**Acceptance**: criterios de Eliminación (backend) de la spec.

---

### B4 — Tests backend

**Agent**: QA · **Depends on**: B1, B2, B3 · **Estimación**: 3 h

`backend/tests/test_portfolios.py`: orden descendente; búsqueda por
display_name y por filename; escapado de `%`/`_`; rango de fechas inclusivo y
422 invertido; paginación (total, página fuera de rango); PATCH válido/vacío/
largo/404; DELETE limpia feedback+decisiones+slides, tolera archivo ausente,
409 en job PROCESSING, 404 repetido. Usar `TestClient` o llamadas directas a
los handlers con `db_session` (seguir el patrón existente de tests de API si
lo hay; si no, handlers directos).

**Files**: `backend/tests/test_portfolios.py` (nuevo)
**Acceptance**: criterio transversal; suite backend completa en verde.

---

### F1 — Servicio Angular + listado con filtros y paginador

**Agent**: Frontend Dev · **Depends on**: contrato del design doc (no de B1) · **Estimación**: 3-4 h

`brand.service.ts`: `getLibraryPortfolios` con params + tipo `PortfolioPage`;
componente: búsqueda con debounce 300 ms, selectores date_from/date_to,
paginador (solo si >1 página), reset a página 1 al cambiar filtros, estado
vacío con mensaje. CSS propio del componente.

**Files**: `frontend/src/app/services/brand.service.ts`,
`frontend/src/app/pages/asset-library/asset-library.component.{ts,html,css}`
**Acceptance**: criterios de Listado/Paginación/Búsqueda (frontend) de la spec.

---

### F2 — Renombrado inline + modal de eliminación

**Agent**: Frontend Dev · **Depends on**: F1 · **Estimación**: 3 h

Edición inline del nombre (Enter confirma / Escape cancela, refresco con la
respuesta del PATCH); modal de confirmación de borrado con el nombre visible
(reutilizar patrón de modal existente si lo hay); tras borrar, reload de la
página actual con retroceso si queda vacía.

**Files**: `frontend/src/app/services/brand.service.ts` (PATCH/DELETE),
`frontend/src/app/pages/asset-library/asset-library.component.{ts,html,css}`
**Acceptance**: criterios de Renombrado/Eliminación (frontend) de la spec.

---

### F3 — Tests frontend

**Agent**: QA (frontend) · **Depends on**: F1, F2 · **Estimación**: 2 h

Specs Karma: servicio (params correctos en la URL, PATCH/DELETE), componente
(cambio de filtro → página 1, confirmación del modal dispara DELETE,
cancelación no llama nada, ítem desaparece tras borrar).

**Files**: `frontend/src/app/services/brand.service.spec.ts`,
`frontend/src/app/pages/asset-library/asset-library.component.spec.ts`
**Acceptance**: `npx ng test --watch=false --browsers=ChromeHeadless` en verde.

---

### D1 — Verificación DevOps (CI/CD y deploy)

**Agent**: DevOps · **Depends on**: B4, F3 (corre tras el merge) · **Estimación**: 0.5 h

**Evaluación previa del Arquitecto: cero cambios requeridos en `ci_cd.yml`**
(tests backend y frontend ya cubren las suites completas; el ALTER de
`display_name` se aplica solo al arrancar; sin env vars nuevas). Checklist
post-deploy:
- [ ] Run de CI del merge en verde (ambos jobs: pytest y Karma).
- [ ] `SELECT column_name FROM information_schema.columns WHERE table_name='generation_jobs' AND column_name='display_name';` en EC2.
- [ ] Smoke: `GET /api/library/portfolios?page=1&page_size=5` devuelve envelope ordenado.
- [ ] Pestaña Portfolios carga con paginador en producción.

**Files**: ninguno (verificación)
**Acceptance**: checklist completo y reportado.

---

### T1 — Documentación

**Agent**: Tech Writer · **Depends on**: none · **Estimación**: 1 h

CLAUDE.md (envelope nuevo del endpoint de portfolios y regla de estados
terminales para DELETE), entrada en `docs/operations/post-deploy-alignment.md`
(solo el ALTER automático — sin comandos manuales), estado de la spec.

**Files**: `GuepardAI/CLAUDE.md`, `docs/operations/post-deploy-alignment.md`,
`docs/specs/gestion-portfolios.md`

---

## Resumen

| Agente | Tareas | Horas est. |
|---|---|---|
| Backend Dev | B1, B2, B3 | 7-8 h |
| Frontend Dev | F1, F2 | 6-7 h |
| QA | B4, F3 | 5 h |
| DevOps | D1 (verificación) | 0.5 h |
| Tech Writer | T1 | 1 h |

**Arranque propuesto**: B1+B2+B3 y F1 en paralelo (backend y frontend no
comparten archivos; F1 trabaja contra el contrato del design doc).
