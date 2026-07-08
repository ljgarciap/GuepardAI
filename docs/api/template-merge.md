# API — Template Merge

Referencia de `/api/template-merge/*`. Implementación: `backend/routers/template_merge.py`
(rutas — migradas desde `main.py` en v2 Fase 1), `backend/services/templates/*`
(orquestador, traversal, analyzer, content, renderer), `backend/models.py`
(`TemplateMergeJob`).

Spec: `docs/specs/template-merge.md`, `docs/specs/template-merge-job-history.md`,
`docs/specs/template-merge-v2-quality.md`
Design: `docs/designs/template-merge.md`, `docs/designs/template-merge-job-history.md`,
`docs/designs/template-merge-v2-quality.md`
ADRs: `docs/ai/contracts/default-llm-template-merge-content-adr-v2.md` (contenido
por slide; supersede al v1), `docs/ai/contracts/default-llm-template-merge-outline-adr.md`
(plan narrativo, Fase 2), `docs/ai/contracts/vision-template-merge-visual-qa-adr.md`
(QA visual, Fase 4, gated)

Toma un PPTX existente como blueprint de layout (fuentes, fondos, imágenes,
estructura) + un documento de conocimiento ya ingerido en el RAG, y genera un
PPTX nuevo preservando el diseño pero reemplazando el texto con contenido
sintetizado por LLM.

Todas las rutas requieren `Authorization: Bearer <access_token>` y aplican el
scoping por tenant estándar (`check_brand_tenant_access`/`check_job_tenant_access`/
`tenant_brand_ids_filter` — ver `docs/api/auth-and-users.md`). `brand_id` es
opcional en la creación del job; un job sin `brand_id` solo es accesible para
`superadmin` (mismo criterio que `GenerationJob`, no específico de este feature).

## Flujo de un job

`POST /template-merge/upload-template` (registra el blueprint) →
`POST /template-merge/jobs` (encola el merge) →
`GET /template-merge/jobs/{id}` (poll de progreso) →
`GET /template-merge/jobs/{id}/download` (descarga el resultado).

El histórico persistente (`GET/PATCH/DELETE /template-merge/jobs`) es
independiente de ese flujo — no participa del pipeline, solo lista/gestiona
jobs ya completados.

## Endpoints

### `POST /api/template-merge/upload-template`

Sube un `.pptx` y lo registra como `BrandAsset` con `category=pptx_template`.

**Body**: `multipart/form-data` — `file` (.pptx), `brand_id` (opcional).

**Respuestas**: `200` → `{ asset_id, filename, category }` · `400` → archivo no es `.pptx`.

### `POST /api/template-merge/jobs`

Crea y encola un `TemplateMergeJob` (Celery: `celery_run_template_merge`).

**Body**:
```json
{
  "template_asset_id": "int (BrandAsset con category=pptx_template)",
  "knowledge_filename": "string (ya ingerido en el RAG)",
  "prompt": "string",
  "brand_id": "int | null",
  "display_name": "string | null"
}
```

**Respuestas**: `200` → `{ job_id, status: "pending", message }` · `404` → el asset no existe o no es `pptx_template` · `403` → el asset o el `brand_id` pertenecen a otro tenant.

### `GET /api/template-merge/jobs/{job_id}`

Poll de progreso del job (pipeline: `pending → processing → completed|error`).

**Respuestas**: `200` → `{ job_id, status, progress, current_step, error_detail, output_url, display_name, created_at, merge_report, merge_summary }` · `404` → no existe o no accesible para el tenant del usuario.

**`merge_report`** (v2, `null` en jobs pre-v2): resultado por slot de texto —
```json
{
  "slides": [
    { "slide": 0,
      "slots": [ { "key": "42", "name": "Title 1", "role": "title", "action": "rewrite", "outcome": "rewritten" } ],
      "preserved_shapes": 3 }
  ],
  "summary": { "rewritten": 0, "adapted": 0, "preserved": 0, "unfilled": 0, "kept_original": 0, "failed": 0 }
}
```
`key` usa el esquema de traversal (`"42"` shape, `"42/17"` hijo de grupo, `"42:r2c3"` celda de tabla).
Outcomes: `rewritten`/`adapted` (texto reemplazado), `preserved` (intocable por diseño),
`unfilled` (el RAG no tenía datos → texto blanqueado, según `tm_empty_rewrite_policy`),
`kept_original` (se conservó el texto del template), `failed` (error puntual; el job continúa).
`merge_summary` es el atajo a `merge_report.summary`.

**`merge_report.visual_qa`** (Fase 4, solo si `tm_visual_qa_enabled=true`): pase
consultivo de Vision LLM sobre el deck renderizado —
`{ "status": "ok|unavailable|failed", "slides_reviewed": n, "total_findings": n,
"slides": [{ "slide": 1, "findings": [{ "type": "overflow|contrast|overlap",
"severity": "high|medium|low", "detail": "..." }] }] }`. Nunca modifica el deck ni
falla el job; con el gate apagado la clave no existe.

### `GET /api/template-merge/jobs/{job_id}/download`

Descarga el `.pptx` resultante. **Requiere fetch autenticado a blob** (`triggerBlobDownload` en `frontend/src/app/utils/download.util.ts`) — un `<a href download>` o `window.open` no llevan el header `Authorization` y devuelven 401.

**Respuestas**: `200` → archivo (`Content-Disposition: attachment`) · `409` → job no completado · `404` → job inexistente/no accesible, o archivo ausente en disco.

### `GET /api/template-merge/templates`

Lista `BrandAsset` con `category=pptx_template` disponibles para elegir como blueprint.

**Query**: `brand_id` (opcional).

**Respuestas**: `200` → `[{ id, filename, description, brand_id, created_at }]`.

---

## Histórico persistente (Gestión — `docs/specs/template-merge-job-history.md`)

Mismo patrón que `GET/PATCH/DELETE /api/library/portfolios` (`docs/api/auth-and-users.md`
no lo cubre; ver `main.py:list_library_portfolios` como referencia de diseño), aplicado
a `TemplateMergeJob` en vez de `GenerationJob`.

### `GET /api/template-merge/jobs`

Listado paginado de jobs **completados**, más reciente primero.

**Query**: `brand_id` (opcional, valida tenant), `search` (contra `display_name`/`output_path`, comodines LIKE escapados), `date_from`/`date_to` (`YYYY-MM-DD`, inclusivos), `page` (default 1), `page_size` (default 12, máx 100).

**Respuestas**:
- `200` → `{ items: [{ id, filename, display_name, created_at, brand_id }], total, page, page_size }`
- `422` → `date_from > date_to`
- `403` → `brand_id` de otro tenant

Sin `brand_id` explícito, el listado se filtra automáticamente a los brands
del tenant del usuario (`superadmin` ve todos). Solo incluye `status="completed"`
— ver merges fallidos (`status="error"`) no está soportado en esta iteración
(decisión del Architect, no bloqueante; ver Open questions del spec).

### `PATCH /api/template-merge/jobs/{job_id}`

Renombra la etiqueta visible (`display_name`). No toca el archivo físico ni `output_path`.

**Body**: `{ "display_name": "string (1-120 chars tras trim)" }`

**Respuestas**: `200` → `{ id, display_name, filename }` · `422` → vacío o > 120 chars · `404` → no existe o no accesible para el tenant.

### `DELETE /api/template-merge/jobs/{job_id}`

Elimina el registro y su archivo físico (`output_path`, tolerante a ausencia).

**Respuestas**: `200` → `{ deleted: true, id }` · `409` → job en `pending`/`processing` (protege el pipeline Celery) · `404` → no existe, no accesible, o ya borrado.
