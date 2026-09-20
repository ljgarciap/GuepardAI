# Spec: Synthesis Studio v2 — Quality Ceiling (Detail-Elicitation Findings)

**Date**: 2026-09-20
**Requested by**: Luis
**Status**: Draft — ready for Architect design
**Project**: GuepardAI
**Assessment**: `docs/designs/synthesis-studio-v2-assessment.md` (2026-07-08, verdict + 3 levers)
**Owner of this document**: `synthesis-studio-analyst` agent

---

## Problem

Luis's "estoy cerca, pero aún hay detalles" about the classic generation pipeline
was not yet specifiable (assessment §3, Lever 3). This spec closes that gap: 4 real
decks were generated on the real Tesco brand (same real prompt Luis has used before
— the Clubcard pitch to Ken Murphy — varying tier and output format), reviewed
slide-by-slide in an interactive gallery, and every mark was traced back to the exact
code path that produced it (per the `synthesis-studio-analyst` mandate: verify before
asking).

Luis's headline observation — **"todas usaron el mismo layout, seguimos en el mismo
círculo"** — turned out to be **mostly two vocabulary-mismatch bugs, not a
fundamental architecture gap**. This materially changes the assessment's own
prioritization: Lever 1 (Brand Grammar Mining — expensive, weeks of work) is very
likely premature until these cheaper fixes are live and re-measured.

## Detail-elicitation session

**Method**: 4 decks generated end-to-end through the real production pipeline
(`AgentOrchestrator.run_generation_pipeline`, no mocks, real LLM calls), same brand
(Tesco, id=1, the only brand with full ingestion available), same prompt, varying
tier/output_format:

| Deck | Tier | Format | Slides | QA forzado |
|---|---|---|---|---|
| A | standard | pptx | 17 | 13 (76%) |
| B | standard | pdf_artistic (legacy) | 20 | 11 (55%) |
| C | premium | pdf_artistic | 18 | 13 (72%) |
| D | premium | pptx | 17 | 13 (76%) |

72 slides reviewed in an interactive artifact gallery (screenshots + `layout_type` +
QA-forced badge per slide). Luis marked 13 slides in deck A (slides 5–17, ranked
`molesta`/`nice`, no free-text notes) and flagged verbally that the repetition was
the real issue — confirmed and root-caused against the actual code path per slide
(`layout_slug`, `ArtDirectorDecision` audit rows), not just the visual impression.

## Detail inventory (mark → root cause → lever)

### Finding 1 — PPTX path: 4 of 5 Analyst layout choices silently collapse to one [FIXED]

**Classification**: Composición/layout genericness → looked like Lever 1, was actually a bug.

`prompt_analyst_v3` ("GRAMMAR TYPE RULES: use EXACTLY these values") instructs the
LLM to choose from exactly 5 words: `hero`, `split`, `data_grid`, `pillars`,
`custom_canvas`. `GRAMMAR_TO_PAINTER` (`services/rendering/painter_bridge.py`), the
dict that translates that choice into a `GammaPainter` method, had **no key** for 4
of those 5 — only `data_grid` matched by accident. Every other choice fell through
`GRAMMAR_TO_PAINTER.get(layout_type, "composition_split")` to the same default.

**Evidence**: deck D (premium/pptx) — 12 of 17 slides (`pillars`×7 + `custom_canvas`
×4 + `split`×1) all silently painted as `composition_split`. Visually confirmed on
deck B (legacy PDF, same class of bug, see Finding 2): slides declared `split`,
`pillars`, and `quote` rendered pixel-identical.

**Fix shipped this session** (`services/rendering/painter_bridge.py`): added
`hero`→`composition_hero`, `split`→`composition_split`, `pillars`→
`composition_pillars`. `custom_canvas` is deliberately **not** mapped to its
identity (`paint_custom_canvas`) — see Finding 1b. Regression tests:
`tests/test_painter_bridge_grammar_mapping.py`. Re-generated deck A/D post-fix and
confirmed visually: `pillars` now renders as a genuine 4-column card layout,
distinct from `split`'s image-left/text-right treatment (see QA evidence below).

### Finding 1b — `custom_canvas` has no content builder for the PPTX path [MITIGATED, not fixed]

**Classification**: Rendering defect (dead/incomplete feature) → Lever 2 adjacent, but really its own item.

`GammaPainter.paint_custom_canvas()` paints from `slide_data["elements"]`. Only
`PremiumVisualAgent._build_slides()` (exclusive to the PDF premium path) ever
populates `canvas_elements`; the PPTX path's `RenderPPTXTool` always builds
`PainterSlideData` with `elements=[]`. Dispatching `custom_canvas` correctly (per
Finding 1's fix) exposed this: the slide rendered as a **blank canvas** (background,
logo and footer only, no content) — confirmed with a real re-render.

**Mitigation shipped this session**: `custom_canvas` maps to `composition_split`
(populated, safe) instead of `paint_custom_canvas` (blank) until a real builder
exists. This is the same shape as the `implemented_premium_patterns` runtime
whitelist already used for the premium PDF path (`system_configs`) — worth the same
treatment here (see Acceptance criteria, Phase 2).

### Finding 2 — Legacy PDF path: the fix from `coherencia-artistica-pipeline.md` didn't test the real vocabulary [FIXED]

**Classification**: Composición/layout genericness → same root cause family as Finding 1.

`resolve_legacy_pdf_layout()`/`GRAMMAR_TO_ARTISTIC_PDF` (`artistic_pdf_service.py`,
shipped and QA-approved 2026-09-18) was validated against the canonical
`GRAMMAR_GEOMETRIES` vocabulary (`cover_hero`, `executive_quote`, `two_column`, …).
But `render_agent.py`'s legacy-PDF branch feeds it `content_json["layout_type"]`,
which is the **Outline Generator's own vocabulary**
(`composition_hero`/`composition_split`/`composition_quote`/`composition_pillars`/
`data_grid_cards`) — a different vocabulary that `GRAMMAR_TO_ARTISTIC_PDF` doesn't
recognize (only `data_grid_cards` matches, by coincidence).

**Evidence**: visually confirmed on deck B — slides declared `composition_split`
(slide 2), `composition_pillars` (slide 4), and `composition_quote` (slide 13) all
rendered as the **identical** split template (image left, 4 bullets right, same
pill/label position). My own QA report from 2026-09-18
(`docs/qa/coherencia-artistica-pipeline-2026-09-09.md`) tested the wrong input
vocabulary and did not catch this — noted here for the record, not to relitigate
that spec, since the fix it shipped is still correct for the vocabulary it targeted.

**Fix shipped this session** (`services/rendering/artistic_pdf_service.py`): added
`composition_hero`→`hero`, `composition_split`→`split`, `composition_quote`→
`quote`, `composition_pillars`→`pillars` to `GRAMMAR_TO_ARTISTIC_PDF` (option (a)
below). Regression tests: `tests/test_artistic_pdf_legacy_layout.py`
(`TestGrammarToArtisticPdfRecognizesOutlineVocabulary`). Re-rendered deck B's
already-generated content (no new LLM spend) and confirmed visually: the same 3
slides that rendered pixel-identical before the fix (declared `composition_split`,
`composition_pillars`, `composition_quote`) now render as genuinely distinct split /
4-column-pillars / centered-italic-quote treatments.

Option (b) — making the Outline Generator emit the canonical `GRAMMAR_GEOMETRIES`
vocabulary directly so there is only one vocabulary project-wide — remains a
larger, separate improvement or the Architect to consider (touches
`prompt_content_outline_v3`, an LLM prompt, so it would need its own AI Architect
validation per project convention). Noted below as a related, still-open item: it
would also fix the PPTX path's fallback when `layout_slug` is `None` (~10-20% of
slides), which today still falls back to the same `composition_*` vocabulary and
does **not** match any `GRAMMAR_TO_PAINTER` key either (a smaller residual gap,
not separately fixed this session — see Open Questions).

### Finding 3 — Legacy PDF `data_grid` layout rendered blank in real production [FIXED]

**Classification**: Rendering defect → Lever 2 adjacent (deterministic bug, not a QA/LLM issue).

`render_agent.py`'s legacy-PDF slide-dict construction never forwarded `metrics`
(only `bullets`) — `artistic_data_grid.html` iterates `slide.metrics` to draw its
cards, `slide.section_label` and `slide.subtitle` for its header, none of which were
passed. This directly contradicts a "non-blocking" note in the 2026-09-09 QA report,
which assumed production would populate `metrics` correctly — it does not, at the
`render_agent.py` layer.

**Evidence**: deck B slide 3 (`data_grid_cards`) rendered as a near-blank page
(title only, generic placeholder subtitle) despite the Redactor having produced real
metrics for it.

**Fix shipped this session** (`agents/render_agent.py`): forward `metrics`
(`normalize_metrics`), `section_label`, `subtitle` in the legacy-PDF slide dict, same
as the PPTX path already does. Regression tests:
`tests/test_render_agent_legacy_pdf_metrics.py`. Re-generated deck B post-fix and
confirmed visually: the `data_grid_cards` slide now renders 4 real KPI cards plus a
highlighted closer tile.

### Finding 4 — Premium PDF path: an unimplemented pattern survives from stale legacy data [OPEN — needs a data alignment]

**Classification**: Rendering defect (data hygiene, not a code-path bug) → Lever 2 adjacent.

Deck C's persisted `pattern_type` distribution: `editorial_split`×8,
**`object_as_letter`×6**, `full_bleed_hero`×4. `object_as_letter` is explicitly
**not** in `implemented_premium_patterns` — the whitelist closed by
`coherencia-artistica-pipeline.md` (Task 1) and re-verified by this session's QA
(`docs/qa/coherencia-artistica-pipeline-premium-2026-09-18.md`) should make this
impossible.

**Root cause**: `PremiumVisualAgent._load_patterns()` calls
`get_latest_brand_patterns()`, which reads `BrandPremiumVisualPattern.patterns_json`
**as stored** — no re-filtering at read time. The whitelist (`normalize_executable_
patterns`) only runs at ingestion **write** time. Tesco's `patterns_json` row
predates the whitelist (original ingestion, months ago) and has never been
re-normalized. Both of this session's whitelist fixes (Task 1's ingestion filter,
and today's `_vision_adjust_loop` fix) are correct for the paths they cover — neither
touches already-persisted legacy rows.

**Not fixed this session** (explicitly deferred — Luis chose the vocabulary fixes,
not the data alignment, in this round). This is exactly the shape of problem this
project already has a mechanism for: register a **data alignment**
(`services/core/data_alignment_service.py`, `ALIGNMENT_REGISTRY`) that re-runs
`normalize_executable_patterns()` over every `BrandPremiumVisualPattern.patterns_json`
row and persists the filtered result. Idempotent, no LLM spend, matches the pattern
already documented in `CLAUDE.md` ("Startup alignment layers").

## Quick wins (no design needed — ready for a PM to schedule)

1. ~~Extend `GRAMMAR_TO_ARTISTIC_PDF` with the 4 missing `composition_*` keys~~ —
   done (Finding 2).
2. **Register a data alignment** to re-normalize every existing
   `BrandPremiumVisualPattern.patterns_json` against the current
   `implemented_premium_patterns` whitelist (Finding 4).
3. **Move `custom_canvas` off the Analyst's menu, or build its `elements`
   populator, for the PPTX path** (Finding 1b) — either remove it from
   `prompt_analyst_v3`'s allowed values (versioned as `_v4`, per project convention)
   until a builder exists, or invest in a `_build_canvas_elements()` for
   `render_agent.py`'s PPTX branch mirroring `PremiumVisualAgent`'s.
4. **PPTX path's `layout_slug=None` fallback** (`render_agent.py`, ~10-20% of
   slides where the Analyst call didn't set a slug) reads
   `content_json["layout_type"]` — the Outline's `composition_*` vocabulary — and
   feeds it straight to `GRAMMAR_TO_PAINTER`, which has no bare `composition_*`
   keys either (only the values these keys map *to*). Smaller than Finding 1
   (fewer slides hit this path) but the same bug shape; worth a one-line
   `GRAMMAR_TO_PAINTER` addition (`composition_hero`→itself, etc.) the next time
   this file is touched.

## Acceptance criteria

### Phase 1 — Vocabulary fixes (mostly done)

- [x] `GRAMMAR_TO_PAINTER` recognizes all 5 values `prompt_analyst_v3` can emit;
      each maps to a distinct `GammaPainter`-dispatchable value except the
      deliberate `custom_canvas` → `composition_split` mitigation.
      (`tests/test_painter_bridge_grammar_mapping.py`)
- [x] The legacy PDF slide dict forwards `metrics`/`section_label`/`subtitle`.
      (`tests/test_render_agent_legacy_pdf_metrics.py`)
- [x] `GRAMMAR_TO_ARTISTIC_PDF` recognizes the Outline Generator's `composition_*`
      vocabulary (Finding 2) — parametrized test covering all 5 outline
      `layout_type` values, each resolving to a distinct legacy PDF `layout`.
      (`tests/test_artistic_pdf_legacy_layout.py::TestGrammarToArtisticPdfRecognizesOutlineVocabulary`)
- [ ] A registered data alignment re-normalizes every `BrandPremiumVisualPattern`
      row against `implemented_premium_patterns` (Finding 4) — test confirms a
      fixture row with `object_as_letter` is cleaned after running it, and that
      running it twice is a no-op (idempotency, per project convention).

### Phase 2 — Close the `custom_canvas` gap properly

- [ ] Architect decision recorded: remove `custom_canvas` from
      `prompt_analyst_v3`'s allowed values (versioned `_v4`) vs. build a PPTX
      `elements` populator. Either way, `paint_custom_canvas()` must never be
      reachable with an empty `elements` list in production.

### Phase 3 — Re-measure before committing to Lever 1

- [ ] Re-run this same 4-deck elicitation (or a subset) after Phase 1 ships, with
      Luis re-marking the same slide range. If the "mismo círculo" complaint is
      resolved by the vocabulary fixes alone, Lever 1 (Brand Grammar Mining) drops
      in priority — it should not be scheduled based on this session's marks alone,
      since a meaningful share of what those marks pointed at is now understood to
      be a bug, not a ceiling of the visual-DNA approach.
- [ ] If repetition persists after Phase 1 (i.e. the Analyst genuinely keeps
      choosing the same 1-2 of the now-distinct 5 layouts), that is a real Lever-1-
      shaped finding (the Analyst's own judgment, not a wiring bug) and graduates to
      its own design doc.

## Edge cases and error scenarios

- A brand with no `BrandPremiumVisualPattern` row at all → Finding 4's alignment is
  a no-op for it (nothing to clean), consistent with `get_latest_brand_patterns()`'s
  existing `[]` fallback.
- The data alignment runs against a brand whose `patterns_json` is already fully
  compliant → no writes, no error (idempotency requirement above).
- `prompt_analyst_v3` gains a 6th value in a future edit → must be added to
  `GRAMMAR_TO_PAINTER` and `GRAMMAR_TO_ARTISTIC_PDF` in the same change, or it
  repeats Finding 1/2. Recommend a shared parametrized test (Phase 1's tests
  already assert every *current* Analyst value has a real mapping — extend it
  rather than trusting manual review next time a value is added.)

## Out of scope

- Lever 1 (Brand Grammar Mining) — explicitly deferred to Phase 3's re-measurement;
  not designed here.
- Rewriting `PremiumVisualAgent` to share a builder with the PPTX path — Finding 1b's
  Quick Win only asks for a decision, not an implementation.
- Any change to `prompt_analyst_v3`'s non-vocabulary instructions (the no-text/
  no-diagram photography rules) — untouched, not implicated by this session's
  findings.
- A second real brand for a broader Lever-1 assessment — this session ran on Tesco
  only (the only fully-ingested brand available); see
  `docs/designs/synthesis-studio-v2-assessment.md` for that open item.

## Open questions

- [Architect] Whether to still pursue Option (b) from Finding 2 (unify the Outline
  Generator onto the canonical `GRAMMAR_GEOMETRIES` vocabulary project-wide) now
  that the surgical fix is live — would also close Quick Win 4 (the PPTX
  `layout_slug=None` fallback) in one move, at the cost of an LLM prompt change
  needing its own AI Architect validation.
- [Architect] Finding 1b: remove `custom_canvas` from the Analyst's menu vs. build
  a PPTX `elements` populator — cost/impact tradeoff.
- [Luis] Whether to schedule Phase 3's re-measurement session now or batch it with
  other pending work (this workspace currently also has the coherencia-artistica-
  pipeline spec's own open items and general backlog).

## References

- `docs/designs/synthesis-studio-v2-assessment.md` — original verdict + 3 levers
- `docs/specs/coherencia-artistica-pipeline.md` — the spec whose legacy-PDF fix
  Finding 2 corrects the test scope of
- `docs/qa/coherencia-artistica-pipeline-premium-2026-09-18.md` — the premium
  whitelist QA that Finding 4 extends (write-time fix; Finding 4 is the read-time/
  legacy-data gap it didn't cover)
- Code: `services/rendering/painter_bridge.py` (`GRAMMAR_TO_PAINTER`),
  `agents/render_agent.py` (`RenderPPTXTool`), `services/generation/analyst_service.py`
  (`get_slide_visual_strategy`), `utils/seed.py` (`prompt_analyst_v3`),
  `services/rendering/premium_visual_agent.py` (`_load_patterns`,
  `get_latest_brand_patterns`)
- Tests added this session: `tests/test_painter_bridge_grammar_mapping.py`,
  `tests/test_render_agent_legacy_pdf_metrics.py`
