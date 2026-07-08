# Design: Histórico persistente de Template Merge

**Date**: 2026-07-07
**Architect**: aprobado
**Spec**: `docs/specs/template-merge-job-history.md`
**Status**: Done — aprobado por Senior Reviewer y QA el 2026-07-07 (ver `docs/reviews/` y `docs/qa/`)
**Rama**: `master` (rama de iteración activa — [[single-active-branch]])

No hay componentes de IA nuevos en este feature (es CRUD + listado sobre un
modelo ya existente) — no se consulta al AI Architect, no aplica ADR.

## Decisiones que resuelven las Open questions del spec

1. **Estado por defecto del listado**: solo `completed`, sin parámetro de
   filtro de estado en esta iteración. Replica exactamente el criterio ya
   usado en `list_library_portfolios` (`GenerationJob`). Ver jobs con
   `error` queda anotado como mejora futura, no bloquea esta entrega.
2. **Refresco History ↔ "THIS SESSION"**: sin polling propio en la pestaña
   History. Se recarga bajo demanda en dos momentos: (a) al activar la
   pestaña History, (b) inmediatamente después de que un job de "THIS
   SESSION" transiciona a `completed` (un solo `loadHistory()` extra dentro
   del `next` del polling existente). Mismo patrón que
   `asset-library.component.refreshLibrary()` — carga on-demand, no
   streaming continuo.
3. **Capa de servicio**: los tres métodos nuevos (`getTemplateMergeJobs`,
   `renameTemplateMergeJob`, `deleteTemplateMergeJob`) van a
   `brand.service.ts`, junto a sus análogos de Portfolios
   (`getLibraryPortfolios`/`renamePortfolio`/`deletePortfolio`) — mismo
   archivo, mismo patrón, un solo cliente HTTP central en el frontend. Las
   llamadas *preexistentes* de `template-merge.component.ts` que usan
   `HttpClient` directo (create/status/download) **no se tocan** — es deuda
   técnica anterior a este feature y queda fuera de alcance (evita
   convertir esta entrega en un refactor no pedido).

## Backend

### Modelo (`models.py`)
Sin cambios de esquema. `TemplateMergeJob` (models.py:493) ya tiene
`display_name`, `created_at`, `status`, `output_path`, `brand_id` — todas
las columnas necesarias. Cero ALTER, cero alineación de datos.

### `GET /api/template-merge/jobs` (nuevo, junto a los existentes en main.py ~1115-1215)

Query params: `brand_id: int = None`, `search: str = None`,
`date_from: date = None`, `date_to: date = None`, `page: int = 1`,
`page_size: int = 12`.

```python
@app.get("/api/template-merge/jobs", tags=["Template Merge"])
def list_template_merge_jobs(
    brand_id: Optional[int] = None,
    search: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = 1,
    page_size: int = 12,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from sqlalchemy import or_

    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be earlier than or equal to date_to.")

    if brand_id:
        check_brand_tenant_access(db, current_user, brand_id)

    query = db.query(models.TemplateMergeJob).filter(models.TemplateMergeJob.status == "completed")
    if brand_id:
        query = query.filter(models.TemplateMergeJob.brand_id == brand_id)
    else:
        tenant_ids = tenant_brand_ids_filter(db, current_user)
        if tenant_ids is not None:
            query = query.filter(models.TemplateMergeJob.brand_id.in_(tenant_ids))
    if search and search.strip():
        pattern = f"%{_escape_like(search.strip())}%"
        query = query.filter(or_(
            models.TemplateMergeJob.display_name.ilike(pattern, escape="\\"),
            models.TemplateMergeJob.output_path.ilike(pattern, escape="\\"),
        ))
    if date_from:
        query = query.filter(models.TemplateMergeJob.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(models.TemplateMergeJob.created_at <= datetime.combine(date_to, datetime.max.time()))

    total = query.count()
    jobs = (query.order_by(models.TemplateMergeJob.created_at.desc())
                 .offset((page - 1) * page_size)
                 .limit(page_size)
                 .all())

    items = [{
        "id": j.id,
        "filename": os.path.basename(j.output_path) if j.output_path else f"Merge_{j.id}.pptx",
        "display_name": j.display_name or (os.path.basename(j.output_path) if j.output_path else f"Merge_{j.id}.pptx"),
        "created_at": j.created_at,
        "brand_id": j.brand_id,
    } for j in jobs]

    return {"items": items, "total": total, "page": page, "page_size": page_size}
```

Reutiliza `_escape_like` y `tenant_brand_ids_filter`/`check_brand_tenant_access`
tal cual existen — no se reimplementan. Sin prefetch de feedback (Template
Merge no tiene tabla de feedback asociada).

### `PATCH /api/template-merge/jobs/{job_id}` (nuevo)

```python
class TemplateMergeRenameRequest(BaseModel):
    display_name: str

@app.patch("/api/template-merge/jobs/{job_id}", tags=["Template Merge"])
def rename_template_merge_job(job_id: int, payload: TemplateMergeRenameRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    job = db.query(models.TemplateMergeJob).get(job_id)
    check_job_tenant_access(db, current_user, job)

    name = (payload.display_name or "").strip()
    if not name or len(name) > 120:
        raise HTTPException(status_code=422, detail="display_name must be between 1 and 120 characters.")

    job.display_name = name
    db.commit()
    return {"id": job.id, "display_name": job.display_name,
            "filename": os.path.basename(job.output_path) if job.output_path else f"Merge_{job.id}.pptx"}
```

### `DELETE /api/template-merge/jobs/{job_id}` (nuevo)

Más simple que el de Portfolios: `TemplateMergeJob` no tiene hijos sin
cascade que limpiar explícitamente (no hay feedback ni decisiones de arte
asociadas).

```python
@app.delete("/api/template-merge/jobs/{job_id}", tags=["Template Merge"])
def delete_template_merge_job(job_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    job = db.query(models.TemplateMergeJob).get(job_id)
    check_job_tenant_access(db, current_user, job)
    if job.status not in ["completed", "error"]:
        raise HTTPException(status_code=409, detail=f"Cannot delete a job while its pipeline is active (status: {job.status}).")

    output_path = job.output_path
    db.delete(job)
    db.commit()

    if output_path:
        try:
            from services.core.storage_service import resolve as resolve_storage
            physical = resolve_storage(output_path)
            if physical and os.path.exists(physical):
                os.remove(physical)
        except Exception:
            pass  # limpieza tolerante — igual que delete_library_portfolio

    return {"deleted": True, "id": job_id}
```

Nota: `status` de `TemplateMergeJob` es un `String(30)` plano
(`"pending|processing|completed|error"`), no un enum como
`GenerationJobStatus` — comparar contra los literales string, no contra un
enum de `models.py`.

## Frontend (Angular 19, standalone, sin libs nuevas)

### `brand.service.ts`
Interfaces nuevas, análogas a `PortfolioItem`/`PortfolioPage`/`PortfolioFilters`:

```typescript
export interface TemplateMergeHistoryItem {
  id: number;
  filename: string;
  display_name: string;
  created_at: string;
  brand_id: number | null;
}

export interface TemplateMergeHistoryPage {
  items: TemplateMergeHistoryItem[];
  total: number;
  page: number;
  page_size: number;
}
```

Métodos nuevos (mismo patrón que `getLibraryPortfolios`/`renamePortfolio`/`deletePortfolio`):
`getTemplateMergeHistory(brandId?, filters?)`, `renameTemplateMergeJob(jobId, displayName)`,
`deleteTemplateMergeJob(jobId)`.

### `template-merge.component.ts` / `.html`
- Nuevo tab-switch local (`activeView: 'session' | 'history' = 'session'`),
  sin router — igual que `asset-library.component.activeTab`.
- Estado nuevo, calcado de `asset-library.component`: `historySearch`,
  `historyDateFrom/To`, `historyPage`, `historyTotal`, `historyItems`,
  `renamingJobId`, `deleteTarget`, `showDeleteModal` — con `Subject` +
  `debounceTime(300)` para la búsqueda (RxJS ya está en uso en el
  componente).
- `inject(BrandService)` se agrega junto al `HttpClient` ya inyectado (no
  se retira el existente, solo se usa para los métodos nuevos).
- Al completar un job en el polling existente (`startPolling`/donde hoy se
  hace `this.completedJobs.unshift(job)`), disparar `this.loadHistory()` si
  `activeView === 'history'` (o simplemente invalidar y recargar la próxima
  vez que se active la pestaña — más simple, se decide en implementación
  sin impacto en el contrato).
- Descarga desde History: **reutiliza** `downloadResult()` ya corregido en
  esta misma sesión (fetch a blob vía `HttpClient` + `triggerBlobDownload`)
  — no se duplica lógica, se le pasa el `job_id` del item de History.
- Modal de confirmación de borrado: mismo patrón visual que
  `asset-library.component` (overlay + card con nombre visible).

## Restricciones (no negociables)

- Sin dependencias npm nuevas.
- Los tres endpoints nuevos van con `Depends(get_current_user)` +
  `check_job_tenant_access`/`check_brand_tenant_access` — cero rutas sin
  scoping de tenant (regla del Senior Reviewer, `CLAUDE.md`).
- El DELETE exige estado terminal — protege el pipeline Celery.
- Pydantic (`TemplateMergeRenameRequest`) para el body del PATCH, no dict crudo.
- Escapado de comodines LIKE en `search` vía `_escape_like` existente.

## Dependencias entre tareas

1. Backend: los 3 endpoints (list/rename/delete) — independientes entre sí,
   un solo PR/tarea razonable (comparten imports y el mismo bloque de main.py).
2. Frontend: `brand.service.ts` (interfaces + 3 métodos) — depende de que el
   contrato de los 3 endpoints esté cerrado (nombres de campo exactos),
   pero puede implementarse en paralelo si el Backend Dev comparte el
   contrato apenas lo tenga.
3. Frontend: `template-merge.component.*` (tab History, filtros, modal) —
   depende de (2).
4. QA: valida sobre (1)+(2)+(3) integrados.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Confundir `status` string de `TemplateMergeJob` con el enum `GenerationJobStatus` al copiar el patrón de Portfolios | Comparar explícitamente contra literales `"completed"`/`"error"`, señalado arriba; cubrir con test backend |
| Doble código de descarga (uno para "THIS SESSION", otro para History) | Un solo método `downloadResult(jobId, displayName)` reutilizado por ambas vistas — no dos implementaciones |
| El usuario espera ver merges fallidos y no puede (solo `completed` listado) | Documentado como decisión explícita del Architect en el spec; si Luis lo pide, es una iteración chica (agregar filtro `status`) |

## Estimación de esfuerzo

| Tarea | Estimación |
|---|---|
| Backend: 3 endpoints + tests pytest | Medio (medio día) |
| Frontend: `brand.service.ts` (interfaces + métodos) | Simple (1-2h) |
| Frontend: tab History en `template-merge.component.*` + tests Karma | Medio (medio día a un día, incluye modal y filtros) |
| QA manual + integración | Simple (1-2h) |

## Evaluación DevOps (CI/CD)

Mismo análisis que `gestion-portfolios.md`: cero cambios en
`ci_cd.yml`. Sin columnas nuevas (no hay ALTER), sin variables de entorno
nuevas, mismo contenedor backend, Nginx ya proxya `/api/*`. Los tests nuevos
(pytest/Karma) corren dentro de las suites existentes sin configuración
adicional.
