# Spec: Generation Pipeline Overhaul

**Date**: 2026-06-12
**Requested by**: Luis
**Status**: Draft
**Project**: GuepardAI

---

## Problem

The generation pipeline has five compounding problems that increase cost, time, and complexity without adding fidelity to the final output:

1. **QA retry loop resets all slides** — when one slide fails QA (deterministic or LLM judge), the orchestrator resets and re-processes all 18 slides, destroying good decisions already made. A 28px resolution shortfall on slide 10 forces a full re-run of 17 slides that were already valid.

2. **AutonomousVLM is permanently broken** — every slide calls a local Ollama model (`qwen2.5vl` at `http://vision:11434`) that was never deployed. 54+ timeouts per generation job, zero successful calls, zero contribution to output quality. The hardcoded fallback geometry is what always runs.

3. **Image generation stack is broken** — `dall-e-3` was removed from OpenAI's API on 2026-05-12. The fallback always fails. Imagen 4.0 standard hits its 70 requests/day quota within 3–4 jobs, leaving the pipeline with no working image generator for the rest of the day.

4. **Layout slug namespace mismatch** — the Art Director LLM consistently outputs `composition_hero`, `composition_split`, `composition_pillars`, etc. The grammar expects `hero`, `split`, `pillars`. Every single slide triggers a forced override. The LLM is being instructed with the wrong vocabulary.

5. **google.generativeai deprecated** — `llm_provider.py` imports the package Google has officially ended support for. Continued use risks silent behavior changes and future breakage.

---

## Solution summary

Five targeted fixes are applied to the generation pipeline, each independent of the others. The QA retry loop is redesigned to evaluate and retry individual failing slides rather than the entire job. AutonomousVLM is removed from the codebase entirely, replacing its call with the hardcoded geometry that was already serving as fallback 100% of the time. The image generation stack is rebuilt with a three-tier routing strategy: `imagen-4.0-fast` (primary, separate quota bucket, half the cost) → `imagen-4.0-standard` (secondary, existing) → `gpt-image-1` (OpenAI fallback, with corrected API contract). The Art Director prompt is corrected to use the grammar's actual layout slugs. The deprecated `google.generativeai` package is replaced with `google.genai` across all text and vision calls. All changes include updated tests. DevOps reviews the spec for CI/CD and Docker Compose implications before implementation begins.

---

## Users and roles

- **End users** (presentation requesters): experience faster generation with fewer wasted retries and a more reliable asset pool.
- **Internal pipeline**: the Celery worker executes the generation job autonomously; no user interaction during the pipeline unless `interactive_mode=True`.
- No permission changes are introduced by this spec.

---

## Acceptance criteria

### Fix 1 — QA retry loop: per-slide evaluation

- [ ] `ScoreFidelityTool.run()` returns a list of per-slide results: `[{slide_number: int, score: float, needs_rework: bool, reasoning: str}]`, not a single global object.
- [ ] The orchestrator reads the per-slide result and resets only slides where `needs_rework=True` to `CONTENT_READY`.
- [ ] Slides where `needs_rework=False` are not touched during a retry iteration.
- [ ] A slide that exhausts `MAX_RETRIES` individual attempts sets `qa_forced=True` on that specific `PresentationSlide` row and is accepted as-is. The job-level `qa_forced` flag is set only if at least one slide has `qa_forced=True`.
- [ ] `ValidateBrandTool` (deterministic) already returns per-slide violations — its integration with the retry loop is unchanged except that only violating slides are reset.
- [ ] A generation job where only slide 3 fails QA completes without re-processing slides 1, 2, 4–N.
- [ ] All existing tests for `ScoreFidelityTool` and `ValidateBrandTool` are updated to reflect the new per-slide return shapes.

### Fix 2 — AutonomousVLM removal

- [ ] `backend/services/rendering/vision_layout_engine.py` is deleted.
- [ ] `PremiumArtDirector._generate_premium_geometry()` in `decoupled_art_director.py` no longer calls `generate_autonomous_layout`. It returns the static fallback geometry directly as a synchronous operation.
- [ ] No `asyncio.to_thread` call exists in `_generate_premium_geometry` after the change.
- [ ] Generation logs no longer contain `[AutonomousVLM]` or `[PremiumArtDirector] Autonomous VLM Design` entries.
- [ ] The `OLLAMA_URL` environment variable reference in `vision_layout_engine.py` is gone. The variable may remain in `llm_provider.py` for any legitimate optional Ollama text/embedding paths.
- [ ] Existing tests that mock or reference `generate_autonomous_layout` or `vision_layout_engine` are removed or updated.

### Fix 3 — Image generation routing

- [ ] Image generation attempts providers in this order: `imagen-4.0-fast-generate-001` → `imagen-4.0-generate-001` → `gpt-image-1`. If all fail, the existing degradation with hard floors runs.
- [ ] `imagen-4.0-fast-generate-001` uses the same `google.genai` SDK call structure as the current standard model, only the model string differs.
- [ ] The OpenAI fallback calls `model="gpt-image-1"` with `size="1536x1024"` and `quality="medium"`. The previous `model="dall-e-3"` and `size="1792x1024"` values are removed.
- [ ] A successful call to any provider saves the asset to the brand's storage path and registers it in `BrandAsset` exactly as before.
- [ ] When `imagen-4.0-fast` returns a 429 quota error, the pipeline transparently falls through to `imagen-4.0-standard` without raising an exception or logging an error — only a warning.
- [ ] When both Imagen variants are quota-exhausted, the pipeline falls through to `gpt-image-1` transparently.
- [ ] Generation logs clearly identify which provider succeeded: `[ImageGen] SUCCESS via imagen-4.0-fast`, `[ImageGen] SUCCESS via imagen-4.0-standard`, `[ImageGen] SUCCESS via gpt-image-1`.
- [ ] **Pre-implementation gate**: Backend Dev must execute `test-ai-request` skill on the server to validate `imagen-4.0-fast` quota and `gpt-image-1` contract before writing code. Results documented in `docs/ai/contracts/`.
- [ ] Unit tests mock all three providers; integration test covers the fallthrough chain.

### Fix 4 — Layout slug alignment

- [ ] The Art Director prompt(s) in `art_director_service.py` and any related prompt in `system_configs` use the grammar's actual layout slugs: `hero`, `split`, `pillars`, `data_grid`, `custom_canvas`. The `composition_*` prefix is removed from all prompt instructions.
- [ ] After the fix, generation logs contain no `LAYOUT OVERRIDE: composition_* ->` entries. The LLM outputs valid slugs directly.
- [ ] The override/correction logic in the Art Director may remain as a safety net but should not be triggered in normal operation.
- [ ] If there are versioned prompt keys in `system_configs` (e.g. `prompt_art_director_v*`), a new versioned key is created per the prompt versioning convention in CLAUDE.md — the existing key is not edited.
- [ ] Tests that assert Art Director output include the corrected slug vocabulary.

### Fix 5 — google.generativeai migration

- [ ] `import google.generativeai as genai` is removed from `llm_provider.py`. All calls previously using `genai` (Gemini text and vision) are migrated to use `from google import genai as google_genai` which is already imported for Imagen.
- [ ] The `FutureWarning` about `google.generativeai` no longer appears in worker startup logs.
- [ ] `requirements.txt` removes `google-generativeai` and confirms `google-genai` is present with a compatible version.
- [ ] All Gemini text and vision calls (chat completions, vision analysis) produce identical outputs before and after the migration — verified by running the existing test suite.
- [ ] Any test that patches `google.generativeai` is updated to patch `google.genai`.

---

## Edge cases and error scenarios

**QA retry:**
- If `ScoreFidelityTool` itself fails (LLM call error) — treat as global pass (do not reset any slides). Log the failure with WARNING level. The existing `qa_forced` fallback handles the quality risk.
- If all slides fail QA simultaneously — all are retried. Same behavior as today for that scenario.
- If a slide fails QA on retry but its `MAX_RETRIES` is already consumed — accept with `qa_forced=True` and continue to render.

**AutonomousVLM removal:**
- `custom_canvas` layout slides — the static fallback geometry was already what ran for 100% of these slides. No visual regression is expected. QA must visually verify at least one `custom_canvas` slide after the change.
- If `decoupled_art_director.py` had other callers of `generate_autonomous_layout` beyond `_generate_premium_geometry` — they must be identified and updated before the file is deleted.

**Image generation routing:**
- If `imagen-4.0-fast` returns `No images in response` (not a quota error) — fall through to next provider. Do not retry the same model.
- If `gpt-image-1` returns a prompt refusal (safety filter) — log the refusal and proceed to degradation. Do not retry with modified prompt (prompt modification is not in this spec).
- If `OPENAI_API_KEY` is not set — skip `gpt-image-1` silently and go to degradation.
- If both `GOOGLE_API_KEY` and `GEMINI_API_KEY` are set — behavior unchanged (existing logic uses `GOOGLE_API_KEY`).

**Layout slug alignment:**
- If a new versioned prompt key is seeded but existing deployed DBs have the old key — the code must read the new key with fallback to the previous key until the DB is seeded. See prompt versioning convention in CLAUDE.md.
- The override/correction logic must remain in place as safety net even after the fix.

**google.generativeai migration:**
- If `google-genai` SDK has a different method signature for vision calls — the Backend Dev must adapt the call, not revert to the old package. The AI Architect must validate the new SDK's vision call contract before implementation.

---

## Out of scope

- Upgrading Google Imagen quota tier. The 70/day limit on `imagen-4.0-standard` is accepted as-is; the routing strategy works around it.
- Adding new image generation providers (Stability AI, Fal.ai, etc.). Out of scope per current provider constraint.
- Improving the quality of the static fallback geometry returned by `PremiumArtDirector` after AutonomousVLM removal. The geometry stays as-is; visual improvement is a separate initiative.
- The `thin_content` slides noted in the final evaluation score (7 slides in the test job). That is a content generation concern, not a pipeline structural concern.
- Any changes to the ingestion pipeline.
- Any changes to the rendering (PPTX/PDF) step beyond what's required for test coverage.
- Resolving the data alignment startup DB connection race (`file_reorganization_v1`, `perceptual_hash_backfill_v1`). Separate fix.

---

## Cross-cutting instructions for PM

> **Tests**: Every task assigned to Backend Dev must include a sub-task for updating the affected tests. No implementation task is complete without its corresponding test update passing. QA will verify test coverage as part of acceptance.

> **DevOps gate**: Before the Architect produces the technical design, DevOps must review this spec and declare:
> - Whether any Docker Compose service or network definition needs updating (e.g., confirming `vision` service removal is safe, confirming no new services are required).
> - Whether `requirements.txt` changes (`google-generativeai` removal, `google-genai` version) require a Docker image rebuild step in the deploy workflow.
> - Whether the CI/CD pipeline (`.github/workflows/`) needs changes to accommodate any of the five fixes.
> DevOps delivers a written sign-off or a list of required YML changes before implementation begins.

---

## Open questions

- [Backend Dev] `imagen-4.0-fast-generate-001` — what is the actual daily quota for this model in the current Google project? Must be confirmed via `test-ai-request` before implementation of Fix 3. If the quota is identical to standard (70/day shared), the routing order still applies but the quota benefit is smaller than expected.
- [Backend Dev] `gpt-image-1` — does the current OpenAI API key have access to this model? Must be confirmed via `test-ai-request`. If not, the OpenAI fallback stays broken and must be documented as a known limitation.
- [Backend Dev] Are there callers of `generate_autonomous_layout` beyond `PremiumArtDirector._generate_premium_geometry`? Grep required before deletion.
- [AI Architect] `google.genai` vision call contract — what is the exact method signature for vision (multimodal) calls in the new SDK vs `google.generativeai`? Must be validated before Fix 5 implementation. Produce ADR in `docs/ai/contracts/`.

---

## References

- Affected files:
  - `backend/providers/llm_provider.py` — Fixes 3, 5
  - `backend/services/generation/decoupled_art_director.py` — Fix 2
  - `backend/services/rendering/vision_layout_engine.py` — Fix 2 (delete)
  - `backend/services/generation/art_director_service.py` — Fix 4
  - `backend/agents/qa_validator.py` — Fix 1
  - `backend/agents/orchestrator.py` — Fix 1
  - `backend/requirements.txt` — Fix 5
  - `backend/utils/seed.py` — Fix 4 (new versioned prompt key)
- AI Decision Records (pending): `docs/ai/contracts/`
- Logs analyzed: generation job 1, 2026-06-12, 1021 seconds, 18 slides
