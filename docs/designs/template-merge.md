# Design: Template Merge Engine

**Date**: 2026-07-04 (backfill — implemented 2026-06-29, commit `8e481ab`; config
refactor + tests added 2026-07-04)
**Architect**: retroactive — see process note below
**Spec**: `docs/specs/template-merge.md`
**Status**: Documented as-built. Approved retroactively by Luis (daily 2026-07-04).

## Process note

This feature was implemented end-to-end (backend services, DB model, 5
endpoints, Celery task, Angular page) directly by Luis without going through
Analyst → Architect → AI Architect first. This document, the spec, and the
ADR were written afterward to bring it in line with the project's standing
process, per the daily on 2026-07-04. Going forward, Tech Writer owns keeping
these three documents in sync with the code (see `.claude/agents/tech-writer.md`
— "Mandatory gate").

## Backend

### Data model (`models.py`)

`TemplateMergeJob` — job tracker, one row per merge request:

| Column | Type | Notes |
|---|---|---|
| `template_asset_id` | FK → `brand_assets.id` | must be `category="pptx_template"` |
| `knowledge_filename` | String(512) | must already be ingested into RAG |
| `prompt` | Text | user's intent, injected into every slide's LLM prompt |
| `status` | String(30) | `pending` \| `processing` \| `completed` \| `error` |
| `current_step` | Text | human-readable progress label |
| `progress` | Integer | 0-100, updated at each pipeline step |
| `output_path` | String(1024) | relative path (via `storage_service.to_relative`) |
| `error_detail` | Text | populated on any pipeline exception |

No new table for template assets — they reuse `BrandAsset` with
`category="pptx_template"`, consistent with how other asset categories
(`photos`, `logos`, `design_elements`) are modeled.

### Pipeline (`services/templates/`)

Four modules, each single-purpose, wired together by
`template_merge_orchestrator.run_template_merge(job_id)`:

1. **`template_analyzer.analyze_template(pptx_path, config)`** — opens the
   PPTX with `python-pptx`, returns one `SlideProfile` per slide containing a
   list of `TextSlot`s. Pure deterministic heuristics, no LLM:
   - Role: placeholder type (`TITLE`/`CENTER_TITLE` → title,
     `SUBTITLE`/`BODY` → body) for placeholder shapes; for non-placeholder
     shapes, position/area heuristics (top fraction → title, tiny area →
     footnote, else body).
   - Char limit: short existing text (≤ `short_hint_threshold` chars, e.g.
     `"$45"`) is treated as a key-metric slot and scaled by a multiplier;
     otherwise title/footnote use fixed limits and body is estimated from
     box area (`chars_per_sq_inch`), clamped to `[body_char_limit_min,
     body_char_limit_max]`.
   - Action: `preserve` (footnotes, legal/confidential keyword matches, short
     non-placeholder labels) → never reaches the LLM. `adapt` (medium-length
     non-placeholder hints) → LLM keeps the same semantic territory.
     `rewrite` (placeholders, long hints) → free LLM replacement.
   - Shape filtering: shapes covering more than `shape_bg_area_threshold` of
     the slide are treated as backgrounds; below `shape_min_area_threshold`
     as decorative dots. Both are skipped entirely (never become slots).

2. **`template_content.generate_slide_contents(profiles, ...)`** — one
   `generate_json()` call per slide (only for slides with at least one
   non-preserved slot), through `providers/llm_provider.py` — no
   `specialization` forced (see ADR). RAG context comes from
   `services/generation/content_service.search_rag()`, scoped to the job's
   `knowledge_filename`, capped at `rag_context_max_chars`. The LLM response
   is unwrapped defensively (`_unwrap_value`) to handle providers that nest
   `{"role": ..., "content": ...}` instead of returning a flat string, then
   markdown-stripped and truncated to the slot's `char_limit` at a word
   boundary. Per-slide failures are caught and degrade to empty strings —
   they never abort the whole job.

3. **`template_renderer.render_merged_pptx(...)`** — copies the template file
   (`shutil.copy2`, original never touched), then for each shape present in
   the slide's content map: captures the `<a:rPr>` element from the first
   non-empty existing run, clears all runs/paragraphs, and writes the new
   text back with that captured formatting reattached run-by-run. Multi-line
   text becomes `<a:br>` soft breaks within the first paragraph rather than
   new paragraphs, keeping the shape's original height/geometry stable.

4. **`template_merge_orchestrator.run_template_merge(job_id)`** — the only
   function that touches the DB directly. Sequence:
   `pending → processing (5%) → analyze (15%) → generate content (35%) →
   render (75%) → completed (100%)`, committing the job's `status`/
   `progress`/`current_step` at each step (`_set_status`). Any exception,
   anywhere in the sequence, is caught at the top level, logged, and persisted
   as `status="error"` + `error_detail` via a **second** DB session (the first
   may be in a bad state after the exception) — this mirrors the resilience
   pattern already used elsewhere in the pipeline (see `docs/specs/fixes-resiliencia-pipeline.md`).

### Configuration (`template_config.py` — added 2026-07-04)

`TemplateMergeConfig` is a dataclass with ~20 tunables (all the thresholds
above). `TemplateMergeConfig.from_db()` reads each one via
`get_system_config()` (ENV override → `system_configs` DB value → hardcoded
default), loaded **once** at the start of `run_template_merge` and threaded
through to the analyzer, content generator, and renderer — no downstream
function queries the DB for config. All `tm_*` keys are seeded in
`utils/seed.py`. This replaced the original commit's hardcoded constants,
following the project's standing rule against hardcoded thresholds
(`asset_score_threshold` / `aspect_ratio_tolerance` precedent in
`art_director_service.py`).

### Endpoints (`main.py`, tag `"Template Merge"`)

| Endpoint | Notes |
|---|---|
| `POST /api/template-merge/upload-template` | multipart upload, `.pptx` only (400 otherwise); stores via `storage_service.brand_assets_dir()`, registers `BrandAsset(category="pptx_template")` |
| `POST /api/template-merge/jobs` | validates asset exists + category, creates `TemplateMergeJob`, enqueues `celery_run_template_merge.delay(job.id)` |
| `GET /api/template-merge/jobs/{id}` | status/progress poll; resolves `output_url` via `storage_service.public_url()` when `output_path` is set |
| `GET /api/template-merge/jobs/{id}/download` | 409 if not `completed`, 404 if job or file missing, otherwise `FileResponse` |
| `GET /api/template-merge/templates` | lists `BrandAsset` rows with `category="pptx_template"`, optional `brand_id` filter |

### Celery (`tasks.py`)

`celery_run_template_merge(job_id)` is a thin wrapper delegating to
`template_merge_orchestrator.run_template_merge` — no business logic in the
task body, consistent with the project rule (Celery tasks are dispatch only).

## Frontend (Angular 19, standalone)

New page at `/template-merge` (`TemplateMergeComponent`): 4-step form
(upload template → select knowledge doc → prompt → review), polls job status
during processing, shows progress, offers download on completion, and keeps
a session history of past merges. No third-party state library — local
component state + the existing HTTP service pattern.

## Testing (added 2026-07-04)

- `backend/tests/test_template_merge.py` — 45 unit tests (no DB, no real
  LLM calls) covering every private heuristic in the four service modules
  plus the orchestrator's control flow with a fully mocked DB session.
- `backend/tests/test_template_merge_integration.py` — 16 integration tests
  against the real test DB (port 5433): all 5 endpoints, plus the full
  pipeline running against a `.pptx` generated in-memory with `python-pptx`.
  File I/O is redirected to a temp tree via `monkeypatch` on
  `storage_service` module constants (same pattern as
  `test_storage_service.py`) — no test writes to `backend/storage/`.
- Combined coverage of `services/templates/`: 88%. The uncovered 12% is
  exception-handling branches for malformed/corrupt PPTX input, not
  unexercised business logic.

## Restricciones (no negociables)

- No direct `anthropic`/`openai`/`mistralai` imports outside
  `providers/llm_provider.py` — `template_content.py` calls `generate_json()`
  only.
- All tunables via `system_configs`, never hardcoded (now satisfied by
  `template_config.py`).
- Celery task bodies stay thin; business logic lives in
  `template_merge_orchestrator.py`.
- The original template file is never mutated — the renderer always works on
  a copy.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Feature shipped without spec/design/ADR review (this document is the retroactive fix) | Tech Writer mandatory gate added to `pm.md`/`tech-writer.md` (2026-07-04) so it can't recur silently |
| LLM providers returning nested objects instead of flat strings | `_unwrap_value()` handles dict/list/stringified-dict cases; covered by unit tests |
| Large/complex real client templates not yet exercised (only synthetic `.pptx` used in automated tests) | Luis's manual local validation (spec acceptance criteria, in progress) is the gate before final close |
