# Technical Design: Generation Pipeline Overhaul

**Date**: 2026-06-12
**Author**: Architect
**Status**: Proposed — pending Luis approval before PM handoff
**Spec**: `docs/specs/generation-pipeline-overhaul.md`

---

## 1. Scope recap

Five independent fixes to the generation pipeline:

| # | Fix | Root cause | Status |
|---|-----|-----------|--------|
| 1 | QA retry per-slide | Global reset destroys good decisions | Ready to design |
| 2 | AutonomousVLM removal | Dead Ollama service with hardcoded fallback | Ready to design |
| 3 | Image generation routing | `dall-e-3` removed; Imagen quota exhausted daily | Gated on ADR + live test |
| 4 | Layout slug alignment | Analyst outputs `composition_*`, grammar expects bare slugs | Ready to design |
| 5 | `google.generativeai` migration | Deprecated package with FutureWarning | Gated on AI Architect ADR |

---

## 2. Implementation gates (must clear before any code)

### Gate A — DevOps sign-off (blocks all fixes)
DevOps reviews this document and declares:
- Whether any Docker Compose service definition changes (e.g., `vision` service — see Fix 2).
- Whether `requirements.txt` changes (Fix 5: `google-generativeai` removal) require explicit Docker rebuild step in deploy workflow.
- Whether CI/CD YMLs need changes for any of the five fixes.

Deliverable: written sign-off or a list of required YML changes committed to `docs/operations/`.

### Gate B — AI Architect ADRs (blocks Fix 3 and Fix 5)
- **Fix 3**: Backend Dev executes `test-ai-request` skill on the server to validate `imagen-4.0-fast-generate-001` daily quota and `gpt-image-1` API contract (especially response format — b64 vs URL). Results in `docs/ai/contracts/imagen-fast-adr.md` and `docs/ai/contracts/gpt-image-1-adr.md`.
- **Fix 5**: AI Architect validates the `google.genai` vision (multimodal) call contract vs the old `google.generativeai` interface. Result in `docs/ai/contracts/google-genai-vision-adr.md`.

---

## 3. Fix 1 — QA retry loop: per-slide evaluation

### 3.1 Problem statement (precise)

`ScoreFidelityTool` evaluates all PLANNED slides in a single LLM call and returns one global `{score, needs_rework, reasoning}` object. When `needs_rework=True`, the orchestrator cannot identify *which* slides failed. Because `violating_slides` is only populated for deterministic QA failures, the LLM judge path always resets all slides to `CONTENT_READY`, forcing a complete re-run of `compose_layout` for all 18 slides.

### 3.2 Design

#### 3.2.1 `ScoreFidelityTool` — return type change

Keep the **single LLM call** (batch is efficient and gives the judge holistic context). Change the output schema the LLM is asked to produce:

**Current prompt output:**
```json
{"score": 0.92, "needs_rework": false, "reasoning": "..."}
```

**New prompt output:**
```json
[
  {"slide_number": 1, "score": 0.92, "needs_rework": false, "reasoning": "..."},
  {"slide_number": 2, "score": 0.45, "needs_rework": true, "reasoning": "Image is a logo in a full-bleed layout."},
  ...
]
```

`ScoreFidelityTool.run()` returns `List[Dict]`. Each item: `{slide_number: int, score: float, needs_rework: bool, reasoning: str}`.

Error handling (edge cases from spec): if the LLM response is not parseable as a list (format failure), treat as global pass — do not reset any slides, log WARNING, rely on `qa_forced` fallback. This preserves the existing fail-open behavior.

The `threshold` logic (score vs flag precedence) is applied per-element in the returned list.

#### 3.2.2 `PresentationSlide` model — two new columns

```python
qa_retry_count = Column(Integer, default=0)   # retries used for this specific slide
qa_forced      = Column(Integer, default=0)   # 1 when retries exhausted; slide accepted as-is
```

Both are additive columns — auto-healed by the startup `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` pattern in `database.py`. **No migration file needed.**

The existing `qa_forced` column on `GenerationJob` is preserved. Its semantics change slightly: it is set to `1` if *at least one* `PresentationSlide.qa_forced = 1` exists for that job.

#### 3.2.3 Orchestrator — loop redesign

The `while retries <= self.MAX_RETRIES` job-level counter is replaced by per-slide retry tracking.

**New flow:**

```
loop:
    compose_layout(job_id, qa_feedback=per_slide_feedback_dict)
    # compose_layout only processes CONTENT_READY slides (existing behavior, unchanged)

    brand_validation = validate_brand(job_id)        # deterministic, already per-slide
    qa_result_list   = score_fidelity(job_id)        # now returns List[Dict] per slide

    # Collect failing slide numbers from both validators
    failing_slides = union of:
        - violating slide_numbers from brand_validation
        - slide_numbers where needs_rework=True from qa_result_list

    if failing_slides is empty:
        qa_passed = True
        break

    slides_to_retry = []
    per_slide_feedback_dict = {}

    for slide_num in failing_slides:
        slide = query PresentationSlide where job_id=job_id AND slide_number=slide_num
        slide.qa_retry_count += 1
        feedback = collect_feedback_for(slide_num, brand_validation, qa_result_list)
        if slide.qa_retry_count >= MAX_RETRIES:
            slide.qa_forced = 1
            # Do NOT reset to CONTENT_READY — accept and continue
        else:
            slide.status = CONTENT_READY
            slides_to_retry.append(slide_num)
            per_slide_feedback_dict[slide_num] = feedback

    db.commit()

    if not slides_to_retry:
        # All failing slides exhausted retries
        job.qa_forced = 1
        qa_passed = True
        break

    # Update job progress + current_step with list of slides being retried
    # Continue loop — compose_layout will only process the reset slides
```

`MAX_RETRIES = 2` on `AgentOrchestrator` is kept as-is (applies per-slide now, not per-job).

#### 3.2.4 `qa_feedback` interface change

`qa_feedback` changes from `Optional[str]` to `Optional[Dict[int, str]]` (slide_number → feedback string) throughout:
- `compose_layout()` signature in `orchestrator.py`
- `compose_layout_for_job()` in `art_director_service.py` (receives `qa_feedback` dict)
- Inside `art_director_service.py`, per-slide injection:
  ```python
  # line ~158 currently:
  if qa_feedback and str(qa_feedback).strip():
      art_direction_note += f"\n\nPREVIOUS QA REJECTION..."

  # becomes:
  slide_feedback = qa_feedback.get(slide.slide_number) if isinstance(qa_feedback, dict) else None
  if slide_feedback:
      art_direction_note += f"\n\nPREVIOUS QA REJECTION (MUST ADDRESS IN THIS ATTEMPT): {str(slide_feedback)[:FEEDBACK_MAX]}"
  ```

#### 3.2.5 Files changed

| File | Change |
|------|--------|
| `backend/agents/qa_validator.py` | `ScoreFidelityTool.run()` — new prompt, new return type `List[Dict]` |
| `backend/agents/orchestrator.py` | Replace job-level while loop with per-slide retry loop; adapt `qa_feedback` handling |
| `backend/models.py` | Add `qa_retry_count`, `qa_forced` to `PresentationSlide` |
| `backend/database.py` | Add `ALTER TABLE presentation_slides ADD COLUMN IF NOT EXISTS qa_retry_count INTEGER DEFAULT 0` and `qa_forced INTEGER DEFAULT 0` to startup schema healing block |
| `backend/services/generation/art_director_service.py` | Change `qa_feedback` param from `str` to `Dict[int, str]`; per-slide lookup |
| `backend/tests/test_qa_validator.py` | Update all tests: `score_fidelity` return shape changes; add per-slide retry orchestrator test |

---

## 4. Fix 2 — AutonomousVLM removal

### 4.1 Problem statement (precise)

`_generate_premium_geometry()` in `PremiumArtDirector` imports and calls `generate_autonomous_layout` from `vision_layout_engine.py`, which posts to `http://vision:11434` (Ollama — never deployed). The call always fails. The `if not geometry or "glass_panels" not in geometry` check catches the failure and runs the hardcoded fallback. The fallback is what 100% of `custom_canvas` slides use. The Ollama call adds 54+ timeout failures per job with no output contribution.

### 4.2 Design

#### 4.2.1 `vision_layout_engine.py` — delete

The file is deleted entirely. It has no callers outside `decoupled_art_director.py` (Backend Dev must confirm with grep before deletion per the spec's open question).

#### 4.2.2 `decoupled_art_director.py` — simplify `_generate_premium_geometry`

The async method becomes synchronous and returns the static geometry directly:

```python
def _generate_premium_geometry(self, title: str, grammar_type: str, design_system: dict, assigned_image: str, slide_number: int) -> str:
    geometry = {
        "glass_panels": [
            {"x_pct": 5, "y_pct": 20, "w_pct": 40, "h_pct": 60,
             "color_hex": "#00539F", "transparency": 0.85,
             "rounded": True, "shadow": True}
        ],
        "image_treatment": {"style": "full_bleed"}
    }
    return json.dumps(geometry)
```

#### 4.2.3 Async simplification

`_generate_premium_geometry` was the only async operation in `_process_slide`. Backend Dev must verify whether `_process_slide` has other `await` calls. If not: simplify `enrich_design` from `asyncio.run(asyncio.gather(...))` to a plain synchronous loop, eliminating the nested event loop. If yes: keep `_process_slide` async but call the now-synchronous `_generate_premium_geometry` directly (no `await asyncio.to_thread`).

#### 4.2.4 No `docker-compose.yml` change needed from this fix alone

The `vision` service was already absent from the deployed compose. Confirm with DevOps during Gate A.

#### 4.2.5 Files changed

| File | Change |
|------|--------|
| `backend/services/rendering/vision_layout_engine.py` | Delete |
| `backend/services/generation/decoupled_art_director.py` | Remove import; make `_generate_premium_geometry` synchronous; simplify `enrich_design` if `_process_slide` has no other async ops |
| `backend/tests/` | Remove any test that mocks `generate_autonomous_layout` or references `vision_layout_engine` |

---

## 5. Fix 3 — Image generation routing

*Gated on Gate B: Backend Dev must execute `test-ai-request` before implementing.*

### 5.1 Problem statement (precise)

`generate_ai_image()` has two tiers: `imagen-4.0-generate-001` (primary, ~70/day quota) and `dall-e-3` (fallback, removed from OpenAI API on 2026-05-12). When Imagen quota is exhausted, the pipeline has no fallback. The DALL-E 3 call also uses `size="1792x1024"` and `model="dall-e-3"` — both invalid.

### 5.2 Design

#### 5.2.1 Three-tier routing in `generate_ai_image()`

```
Tier 1: imagen-4.0-fast-generate-001   (same SDK, separate quota bucket, $0.02/image)
Tier 2: imagen-4.0-generate-001        (existing primary, moved to secondary)
Tier 3: gpt-image-1                    (OpenAI, size=1536x1024, quality=medium, b64_json)
```

Each tier: on any exception, log WARNING `[ImageGen] <provider> failed: <reason>. Falling through to next tier.` then continue to next tier. On success, log `[ImageGen] SUCCESS via <provider>`.

#### 5.2.2 Tier 1 implementation

Identical to current Tier 2 (Imagen 4.0 standard), only the model string changes:
```python
model='imagen-4.0-fast-generate-001'
```

#### 5.2.3 Tier 3 (`gpt-image-1`) contract

The `gpt-image-1` response returns base64-encoded image bytes, not a URL. The call and save pattern:
```python
response_openai = client_openai.images.generate(
    model="gpt-image-1",
    prompt=clean_prompt,
    size="1536x1024",
    quality="medium",
    n=1,
)
if response_openai and response_openai.data:
    import base64
    img_bytes = base64.b64decode(response_openai.data[0].b64_json)
    with open(output_path, "wb") as f:
        f.write(img_bytes)
```

The `requests.get(image_url)` URL-fetch pattern from the DALL-E 3 code is removed entirely.

#### 5.2.4 Log identifiers (spec requirement)

- `[ImageGen] SUCCESS via imagen-4.0-fast`
- `[ImageGen] SUCCESS via imagen-4.0-standard`
- `[ImageGen] SUCCESS via gpt-image-1`

#### 5.2.5 Files changed

| File | Change |
|------|--------|
| `backend/providers/llm_provider.py` | Replace two-tier routing with three-tier; update DALL-E 3 → gpt-image-1 contract |
| `backend/tests/test_llm_provider.py` (new or existing) | Mock all three providers; test fallthrough chain; test b64 save path |

---

## 6. Fix 4 — Layout slug alignment

### 6.1 Problem statement (precise)

The Analyst prompt (`prompt_analyst_v1`, `prompt_analyst_v2`) instructs the LLM to output `grammar_type` values from the set `{composition_hero, composition_split, composition_quote, composition_pillars, data_grid_cards}`. The grammar (`GRAMMAR_GEOMETRIES`) expects `{hero, split, pillars, data_grid, custom_canvas}`. Every slide where `grammar_type = "composition_split"` causes `get_layout_geometry()` to miss, triggering a layout override. This is the source of all `LAYOUT OVERRIDE: composition_* ->` log entries.

The Art Director prompt (`prompt_art_director_v2`) also references `composition_split` and `composition_hero` in its design instructions, reinforcing the wrong vocabulary.

### 6.2 Design

#### 6.2.1 New prompt keys in `seed.py`

Two new keys (existing keys are NOT edited — seeder skips them on deployed DBs):

**`prompt_analyst_v3`**: identical to `prompt_analyst_v2` with `grammar_type` vocabulary corrected:
```
- "hero": Cover or Section Breaks.
- "split": Content with supporting image.
- "data_grid": Quantitative data and KPIs.
- "pillars": 3-4 distinct columns.
- "custom_canvas": Full creative freedom.
```

**`prompt_art_director_v3`**: identical to `prompt_art_director_v2` with `composition_split` and `composition_hero` replaced by `split` and `hero` in design instructions 1 and 5.

#### 6.2.2 Code changes for prompt key lookup

Wherever the Analyst prompt is read (Backend Dev locates the exact call in `content_service.py` / `content_engine.py`):
```python
prompt_tpl = db.query(...).filter(key == "prompt_analyst_v3").first()
if not prompt_tpl:
    prompt_tpl = db.query(...).filter(key == "prompt_analyst_v2").first()
```

`art_director_service.py` (already has a v2→v1 fallback chain, extend to v3→v2→v1):
```python
prompt_tpl = db.query(...).filter(key == "prompt_art_director_v3").first()
if not prompt_tpl:
    prompt_tpl = db.query(...).filter(key == "prompt_art_director_v2").first()
if not prompt_tpl:
    prompt_tpl = db.query(...).filter(key == "prompt_art_director_v1").first()
```

#### 6.2.3 Default value fix

`art_director_service.py` line 161:
```python
analyst_grammar_type = strategy.get("grammar_type", "composition_split")
# becomes:
analyst_grammar_type = strategy.get("grammar_type", "split")
```

#### 6.2.4 Override safety net

The existing override/correction logic in `art_director_service.py` (lines 435-489) stays in place unchanged. After this fix, it should not trigger in normal operation but remains as a safety net.

#### 6.2.5 Files changed

| File | Change |
|------|--------|
| `backend/utils/seed.py` | Add `prompt_analyst_v3` and `prompt_art_director_v3` |
| `backend/services/generation/art_director_service.py` | Extend fallback chain to v3; fix default slug |
| `backend/services/generation/content_service.py` or `content_engine.py` | Extend fallback chain to `prompt_analyst_v3` |
| `backend/tests/` | Update any test asserting Art Director/Analyst prompt output to use corrected slug vocabulary |

---

## 7. Fix 5 — `google.generativeai` migration

*Gated on Gate B: AI Architect must produce ADR for google.genai vision call contract.*

### 7.1 Problem statement (precise)

`llm_provider.py` line 7 imports `google.generativeai as genai`. The `google-genai` SDK (used for Imagen, already imported at line 14 as `google_genai`) is the current Google-supported SDK. The deprecated package produces `FutureWarning` on every worker startup and risks silent behavior changes.

### 7.2 Design

#### 7.2.1 Migration scope

All `genai.*` calls in `llm_provider.py` are migrated to use `google_genai` (already imported). The AI Architect ADR will document the exact method signatures for both text (chat completions) and vision (multimodal) calls to ensure behavioral parity.

High-level migration pattern (exact contract from ADR):
- `genai.configure(api_key=...)` → `client = google_genai.Client(api_key=...)`
- `genai.GenerativeModel("gemini-...")` → model addressed via `client.models.*`
- `model.generate_content(...)` → `client.models.generate_content(model=..., contents=[...])`
- Vision calls (multimodal) → per ADR; exact signature validated against live API before implementation

#### 7.2.2 `requirements.txt`

- Remove: `google-generativeai`
- Confirm present: `google-genai>=1.0.0` (exact minimum from ADR)

#### 7.2.3 Files changed

| File | Change |
|------|--------|
| `backend/providers/llm_provider.py` | Remove `import google.generativeai as genai`; migrate all `genai.*` calls |
| `backend/requirements.txt` | Remove `google-generativeai`; pin `google-genai` |
| `backend/tests/` | Update patches from `google.generativeai` to `google.genai` |

---

## 8. Task breakdown

### Task dependencies

```
Gate A (DevOps)
    │
    ├──▶ Fix 2 (AutonomousVLM removal)   [1 SP, ~4h]
    ├──▶ Fix 4 (Layout slug alignment)   [2 SP, ~8h]
    └──▶ Fix 1 (QA per-slide retry)      [3 SP, ~12h]

Gate B (AI Architect ADRs + live test)
    │
    ├──▶ Fix 3 (Image routing)           [2 SP, ~8h]
    └──▶ Fix 5 (google.genai migration)  [2 SP, ~8h]
```

Fixes 1, 2, and 4 can run in parallel after Gate A clears. Fixes 3 and 5 can run in parallel after Gate B clears. Fixes 1-4 have no interdependency with Fixes 3 and 5.

### Task list for PM

---

**TASK 0 — DevOps: Gate A sign-off**
Assignee: DevOps
Input: this design document + spec
Output: written sign-off or list of YML changes needed
Effort: 0.5 SP
Acceptance: written response committed to `docs/operations/devops-gate-pipeline-overhaul.md`

---

**TASK 1 — AI Architect: Gate B ADRs (Fix 3 + Fix 5)**
Assignee: AI Architect + Backend Dev (for live test)
Sub-tasks:
- Backend Dev executes `test-ai-request` for `imagen-4.0-fast-generate-001` and `gpt-image-1`
- AI Architect validates `google.genai` vision call contract
- ADRs committed to `docs/ai/contracts/`
Effort: 1 SP
Acceptance: three ADR files present in `docs/ai/contracts/`

---

**TASK 2 — Backend Dev: Fix 2 (AutonomousVLM removal)**
Assignee: Backend Dev
Depends on: Task 0 (Gate A)
Files: `vision_layout_engine.py` (delete), `decoupled_art_director.py`
Sub-tasks:
- Grep `generate_autonomous_layout` callers — confirm no callers outside `_generate_premium_geometry`
- Delete `vision_layout_engine.py`
- Simplify `_generate_premium_geometry` to synchronous static return
- Evaluate `_process_slide` async necessity; simplify `enrich_design` if warranted
- **Update tests**: remove mocks for `generate_autonomous_layout`; add test asserting static geometry is returned
Effort: 1 SP
Acceptance: all spec acceptance criteria for Fix 2; no `[AutonomousVLM]` log entries in test run

---

**TASK 3 — Backend Dev: Fix 4 (Layout slug alignment)**
Assignee: Backend Dev
Depends on: Task 0 (Gate A)
Files: `seed.py`, `art_director_service.py`, `content_service.py` / `content_engine.py`
Sub-tasks:
- Add `prompt_analyst_v3` to seed.py (corrected grammar type vocabulary)
- Add `prompt_art_director_v3` to seed.py (corrected design instruction language)
- Extend fallback chains in art_director_service and content service
- Fix default slug `"composition_split"` → `"split"`
- **Update tests**: assert prompts use corrected vocabulary; assert no `LAYOUT OVERRIDE: composition_*` in generation log
Effort: 2 SP
Acceptance: all spec acceptance criteria for Fix 4

---

**TASK 4 — Backend Dev: Fix 1 (QA per-slide retry)**
Assignee: Backend Dev
Depends on: Task 0 (Gate A)
Files: `qa_validator.py`, `orchestrator.py`, `models.py`, `database.py`, `art_director_service.py`
Sub-tasks:
- Add `qa_retry_count` and `qa_forced` columns to `PresentationSlide` in `models.py`
- Add `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` entries to `database.py` startup block
- Rewrite `ScoreFidelityTool.run()` prompt and return type
- Rewrite orchestrator QA loop (per-slide tracking, `qa_feedback` dict)
- Update `art_director_service.py` `qa_feedback` injection to per-slide
- **Update tests**: `ScoreFidelityTool` returns `List[Dict]`; orchestrator test where only slide 3 fails does not reset slides 1-2 or 4-N; test `qa_forced` set on slide and job when retries exhausted
Effort: 3 SP
Acceptance: all spec acceptance criteria for Fix 1

---

**TASK 5 — Backend Dev: Fix 3 (Image generation routing)**
Assignee: Backend Dev
Depends on: Task 1 (Gate B — imagen-4.0-fast and gpt-image-1 ADRs)
Files: `llm_provider.py`
Sub-tasks:
- Implement three-tier routing
- Tier 1: imagen-4.0-fast (same SDK pattern)
- Tier 3: gpt-image-1 with b64_json decode (no URL fetch)
- Per-tier success/warning log identifiers
- **Update tests**: mock all three providers; test fallthrough when Tier 1/2 raise exception; test Tier 3 b64 decode path; test silent skip when `OPENAI_API_KEY` absent
Effort: 2 SP
Acceptance: all spec acceptance criteria for Fix 3

---

**TASK 6 — Backend Dev: Fix 5 (google.genai migration)**
Assignee: Backend Dev
Depends on: Task 1 (Gate B — google.genai vision ADR)
Files: `llm_provider.py`, `requirements.txt`
Sub-tasks:
- Remove `import google.generativeai as genai`
- Migrate all `genai.*` text calls per ADR contract
- Migrate all `genai.*` vision calls per ADR contract
- Remove `google-generativeai` from `requirements.txt`
- **Update tests**: patch `google.genai` instead of `google.generativeai`; run full test suite to confirm behavioral parity
Effort: 2 SP
Acceptance: all spec acceptance criteria for Fix 5; no `FutureWarning` in worker startup log

---

**TASK 7 — Senior Reviewer: review all five fixes**
Assignee: Senior Reviewer
Depends on: Tasks 2–6
Review checklist (from CLAUDE.md Senior Reviewer patterns):
- All LLM calls go through `llm_provider.py` (no direct SDK imports in services)
- `ScoreFidelityTool` calls `self.log_decision()` with per-slide results
- No hardcoded model strings outside `llm_provider.py`
- New `system_configs` keys in `seed.py` (Fix 4 prompts)
- File path operations via `storage_service.py` (Fix 3 output_path unchanged)
- `qa_feedback` dict — no type confusion with legacy string callers

---

**TASK 8 — QA: acceptance validation**
Assignee: QA
Depends on: Task 7
- Run full test suite (`pytest --cov=agents tests/ -v`)
- Verify Fix 1: run generation with a mocked single-slide QA failure; assert other slides not reset
- Verify Fix 2: run generation; assert no `[AutonomousVLM]` log entries
- Verify Fix 4: run generation; assert no `LAYOUT OVERRIDE: composition_*` entries in logs
- Visual verify: at least one `custom_canvas` slide renders correctly after Fix 2

---

## 9. Risks and mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| `gpt-image-1` API key not provisioned on current OpenAI tier | Medium | Fix 3 fallback remains broken | Gate B live test confirms access before code; spec already documents "known limitation" path |
| `google.genai` vision interface differs enough to break multimodal calls | Low | Gemini vision analysis fails silently | AI Architect ADR validates contract on live API; Fix 5 gated on that validation |
| Per-slide QA loop runs more total QA calls (e.g. 18 slides × MAX_RETRIES vs 1 job × MAX_RETRIES) | Low | LLM cost increase | Each QA evaluation is still one LLM call (batch); retry only triggers for actually failing slides — net calls should decrease |
| `prompt_analyst_v3` seeded on new deploys but not on existing prod DB until next restart | Low | Existing prod DB continues with `composition_*` slugs until restart | Acceptable — first deploy restart seeds v3; override safety net catches stragglers |
| `_process_slide` has async ops beyond `_generate_premium_geometry` (unknown) | Low | Simplification of `enrich_design` breaks premium slides | Backend Dev grepped before change; fallback: keep async structure, just make `_generate_premium_geometry` sync |

---

## 10. Out of scope (reconfirmed)

- `imagen-4.0-standard` quota increase (accepted as-is)
- Quality improvement of the static fallback geometry (separate initiative)
- `thin_content` slide quality (content generation concern)
- `file_reorganization_v1` / `perceptual_hash_backfill_v1` startup race (separate fix)
- Ingestion pipeline changes
