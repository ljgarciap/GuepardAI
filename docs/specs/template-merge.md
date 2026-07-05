# Spec: Template Merge Engine

**Date**: 2026-07-04 (backfill — feature shipped 2026-06-29, commit `8e481ab`, without a prior spec)
**Requested by**: Luis
**Status**: Done — shipped; config refactor + unit/integration tests added 2026-07-04. Pending Luis's manual local validation before final close.
**Project**: GuepardAI

## Problem

Some clients hand over a PPTX that already has the exact visual design they
want (fonts, backgrounds, images, layout) — often produced by an external
design agency — and just need it refreshed with new content sourced from a
knowledge document. The existing generation pipeline (Redactor → Architect →
Render) always designs from Guepard's own layout grammar; it has no path for
"keep this exact deck's design, swap the words."

## Solution summary

A new generation mode: upload an existing PPTX as a reusable template asset,
pick a knowledge document already ingested into the RAG, and generate a new
PPTX where every slide's visual structure is preserved exactly (untouched
images, backgrounds, fonts, positions) while the text content is replaced
with LLM-synthesized material grounded in the knowledge base.

## Users and roles

- Single role (current app-wide model): the GuepardAI operator uploads a
  template, selects a knowledge document, writes a prompt describing intent,
  and downloads the merged PPTX once the job completes.

## Acceptance criteria

**Template upload**
- [x] `POST /api/template-merge/upload-template` accepts only `.pptx` files
      (400 otherwise) and registers a `BrandAsset` with `category="pptx_template"`.

**Job creation**
- [x] `POST /api/template-merge/jobs` validates the referenced asset exists
      and has `category="pptx_template"` (404 otherwise), creates a
      `TemplateMergeJob` (`status="pending"`), and enqueues the Celery task.

**Analysis (no LLM)**
- [x] Every text-bearing shape in the template is classified into a role
      (`title` / `body` / `footnote`) and an action
      (`preserve` / `adapt` / `rewrite`) using deterministic heuristics — no
      LLM call for structural analysis.
- [x] Background shapes (>80% of slide area) and decorative dots (<0.5% of
      slide area) are excluded from content slots.
- [x] Shapes carrying legal/confidential keywords (`confidential`,
      `proprietary`, `©`, etc.) are always preserved regardless of length.

**Content generation (RAG + LLM)**
- [x] One LLM call per slide; only slots with `action != "preserve"` are sent.
- [x] Content is grounded in RAG search results scoped to the selected
      `knowledge_filename`.
- [x] Generated text is truncated to each slot's estimated `char_limit`
      (word-boundary truncation with ellipsis), and markdown is stripped.
- [x] A slide with zero active slots or a per-slide LLM/RAG failure does not
      abort the job — it falls back to empty/preserved content and the
      pipeline continues.

**Rendering**
- [x] The output is a **copy** of the template — the original template asset
      file is never modified.
- [x] Text replacement preserves the first non-empty run's formatting
      (font, size, bold, italic, color — RGB or theme) via `<a:rPr>` XML reuse.
- [x] Multi-line generated content becomes soft line breaks (`<a:br>`) within
      the same paragraph, keeping the shape's vertical geometry stable.
- [x] Shapes not present in the content map are left completely untouched.

**Job lifecycle**
- [x] `GET /api/template-merge/jobs/{id}` reports `status`, `progress`,
      `current_step`, `error_detail`, and a servable `output_url` once done.
- [x] `GET /api/template-merge/jobs/{id}/download` returns the `.pptx` file
      only when `status="completed"` (409 otherwise), 404 if the job or the
      output file doesn't exist.
- [x] Any exception anywhere in the pipeline sets `status="error"` with
      `error_detail` populated — the job never gets stuck mid-flight.

**Configuration**
- [x] All thresholds and limits (shape filtering, char limits, RAG k,
      classification cutoffs) are tunable via `system_configs` (`tm_*` keys),
      not hardcoded — added 2026-07-04, see `docs/designs/template-merge.md`.

**Testing**
- [x] Unit tests for role inference, char-limit estimation, action
      classification, LLM response unwrapping, markdown stripping, in-place
      text replacement, and orchestrator state transitions
      (`backend/tests/test_template_merge.py`, 45 tests).
- [x] Integration tests for all 5 endpoints and the full pipeline against a
      real generated `.pptx` (`backend/tests/test_template_merge_integration.py`,
      16 tests). Combined coverage of `services/templates/`: 88%.
- [ ] Luis's manual local validation on real client templates (in progress).

## Edge cases and error scenarios

- **Template asset not found or wrong category** → 404 on job creation.
- **Template file missing on disk** (asset row exists, file deleted/moved)
  → job marked `error` with a specific `error_detail`, never silently skipped.
- **RAG search fails** (e.g. knowledge filename not indexed) → the slide still
  gets an LLM call with empty context; the prompt instructs the LLM to return
  `""` when no relevant data exists rather than inventing content.
- **LLM returns a nested object instead of a plain string** (observed
  behavior from some providers) → unwrapped via known-key extraction, list
  joining, or `ast.literal_eval` on stringified dicts, in that order.
- **Generated content exceeds the slot's char_limit** → truncated at the
  nearest word boundary with a trailing ellipsis, never a hard mid-word cut.
- **Slide has no editable slots at all** (e.g. only images/backgrounds) →
  skipped entirely, no LLM call, no error.
- **Download requested before completion** → 409, not 404 (job exists, just
  not ready).

## Out of scope

- Editing the template's non-text visual elements (images, shape positions,
  colors) — those are always preserved as-is by design.
- Multi-template batch merge in a single job.
- A UI to hand-tune per-slot char limits or role classification before
  generation (the heuristics in `template_analyzer.py` are the only lever;
  runtime tuning is via `system_configs`, not per-job).
- Support for `.ppt` (legacy binary format) or non-PowerPoint inputs.

## Open questions

- None blocking. Retroactively documented — the design was not reviewed by
  the Architect before implementation (see `docs/designs/template-merge.md`
  for the process note). No scope changes are anticipated at this point.

## References

- Backend: `backend/services/templates/` (`template_analyzer.py`,
  `template_content.py`, `template_renderer.py`,
  `template_merge_orchestrator.py`, `template_config.py`), `models.py`
  (`TemplateMergeJob`), `main.py` (5 endpoints under `/api/template-merge/`),
  `tasks.py` (`celery_run_template_merge`).
- Frontend: `frontend/src/app/pages/template-merge/`.
- Tests: `backend/tests/test_template_merge.py`,
  `backend/tests/test_template_merge_integration.py`.
- AI touchpoint: `docs/ai/contracts/default-llm-template-merge-content-adr.md`.
- Original commit: `8e481ab` (2026-06-29).
