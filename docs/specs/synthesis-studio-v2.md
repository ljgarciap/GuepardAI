# Spec: Synthesis Studio v2 — Quality Ceiling (Detail-Elicitation Findings)

**Date**: 2026-09-20
**Requested by**: Luis
**Status**: Phase 1 + Phase 2's Finding 5 done (5 findings fixed, shipped and re-verified against real production data across 2 re-measurement rounds); Quick Win 4 and 1 Architect decision (Finding 2 Option (b)) still open
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

## Phase 2 re-measurement session (2026-09-21)

Same 4-deck matrix regenerated fresh after Findings 1-4 shipped (new job IDs, no
reused data, no mocks). Luis re-marked deck A in full (20/20 slides this time, vs.
13/20 in round 1): 10 `molesta`, 4 `nice`, 6 `ok`, no free-text notes — **not
clearly better** than round 1 by mark count alone, despite Findings 1-4 being
visually confirmed fixed.

Investigated before asking Luis anything further (per the standing rule: verify
against the code path first). Pulled the exact `layout_slug` sequence for all 3
PPTX/legacy-PDF decks (A, B, D) — identical shape in all three:

```
Deck A: hero, pillars, data_grid, pillars, [none], pillars, data_grid, split,
        pillars, data_grid, data_grid, pillars, split, pillars, data_grid,
        data_grid, pillars, data_grid, pillars, data_grid
```

Roughly 80% of each deck alternates between only **2** of the 5 real, now-genuinely-
distinct layouts (`pillars`/`data_grid`, ~8 times each in a 20-slide deck) — `hero`,
`split`, `custom_canvas` barely appear in the body. Findings 1/2 fixed the bug
("5 choices collapsing into 1 rendered result"); this is a **different, second-order
problem**: even with 5 genuinely distinct renders available, the deck settles into a
2-value ping-pong, which still reads as repetitive to a human even though nothing
technically repeats back-to-back.

### Finding 5 — Neither LLM call reasons about the whole deck's layout rhythm [FIXED]

**Classification**: exactly the "if repetition persists after Phase 1... a real
Lever-1-shaped finding (the Analyst's own judgment, not a wiring bug)" case this
spec's Phase 2 anticipated — but cheaper than full Brand Grammar Mining.

**Root cause**: the Art Director's prompt already includes a "VISUAL HISTORY (DO NOT
REPEAT)" section and a variety rule — but that rule only forbids repeating the
*immediately previous* layout, and its history window was hardcoded to the last 3
slides. Alternating `pillars, data_grid, pillars, data_grid, ...` never violates
"don't repeat the last one," so the rule was satisfied while still producing a
2-cycle loop. The **Analyst** (`get_slide_visual_strategy`/`prompt_analyst_v3`) —
which sets the *baseline* `grammar_type` the Art Director's override usually just
confirms — had **zero** deck-level context at all; it decided every slide in
isolation.

**Fix shipped**: a shared helper (`analyst_service.get_recent_layout_history`, window
= `system_configs.layout_diversity_window`, default 6) feeds the same real
`layout_slug` history to both calls. `prompt_analyst_v4` adds the history + an
explicit "don't settle into a 2-layout ping-pong" instruction (new placeholder,
degrades cleanly on older prompt versions per `str.format()`'s standard
unused-kwarg tolerance). `prompt_art_director_v4` strengthens rule #5 to reason over
the *whole* recent-history list, not just its last entry, and widens the window from
a hardcoded 3 to the same shared config. Regression tests:
`tests/test_analyst_layout_diversity.py`. Live-validated (real, non-mocked calls,
adversarial ping-pong history fed deliberately) before the full-deck test — see
`docs/ai/contracts/deck-layout-diversity-adr.md`; the Art Director's own
`visual_reasoning` named the pattern explicitly: *"The visual history shows an
alternating ping-pong between 'pillars' and 'data_grid'... we select
'custom_canvas'."*

**Full-deck confirmation**: regenerated deck A fresh. New `layout_slug` sequence
uses 4 distinct values with real spread (`split`×3 non-fallback + fallback cases,
`pillars`×3, `data_grid`×2, `custom_canvas`×1 out of 16 slides) instead of the prior
strict 2-value alternation — visually confirmed on the rendered PPTX (a `data_grid`
slide showing a 2×2 KPI grid beside a photo, structurally distinct from the
`pillars` 4-card layout). One rough edge surfaced in this same run: a `custom_canvas`
slide (portrait image, mostly blank canvas otherwise) suggests the Art Director
sometimes returns `canvas_elements` with only an image and no accompanying text —
worth watching in a future round, not a regression from this fix (canvas_elements
rendering itself is confirmed correct per Finding 1b; this is a content/composition
call by the LLM, the same class of judgment call the Analyst/Art Director always make).

**Interaction with Quick Win 4 (still open)**: this run also had more slides than
usual fall through to `layout_slug=None` (Art Director skipped providing an
override), which routes through the Outline's `composition_*` vocabulary and mostly
collapses to `composition_split` in the PPTX painter (the known, still-open gap).
Fixing Quick Win 4 would make the *effective* rendered variety match the *decided*
variety more closely — now more visible/valuable given Finding 5's fix, since the
Analyst/Art Director are actively trying to diversify and Quick Win 4 silently
flattens some of that effort back down.

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
`composition_pillars`, `custom_canvas`→`custom_canvas` (identity — see Finding 1b
for why this took two passes). Regression tests:
`tests/test_painter_bridge_grammar_mapping.py`. Re-generated deck A/D post-fix and
confirmed visually: `pillars` now renders as a genuine 4-column card layout,
distinct from `split`'s image-left/text-right treatment (see QA evidence below).

### Finding 1b — `custom_canvas` had no real content builder for the PPTX path [FIXED]

**Classification**: Rendering defect (incomplete feature, not dead) — its own item, bigger than initially scoped.

`GammaPainter.paint_custom_canvas()` paints from `slide_data["elements"]`.
Dispatching `custom_canvas` correctly (per Finding 1's fix) first exposed a blank
canvas (background/logo/footer only) — investigating why led to two real,
independent bugs, not one:

1. **The data existed but never reached either renderer.** The Art Director
   (`art_director_service.py`) already writes `canvas_elements` into
   `PresentationSlide.planning_json["art_director"]["canvas_elements"]` for
   **every** slide, regardless of tier/output_format — it's Architect-step output,
   not a premium-only concept. But `render_agent.py`'s PPTX branch hardcoded
   `PainterSlideData(elements=[])`, and its premium-PDF branch rebuilt a fresh
   `ContentManifestSlide` **without** passing `planning_json` through at all — so
   `PremiumVisualAgent._build_slides()`'s own (correct) read of it always saw `{}`
   too. Both paths were silently discarding real Art Director output.
2. **Neither renderer understood the vocabulary the Art Director actually
   produces.** Real production `canvas_elements` go well beyond the prompt's 3
   illustrative types (text/image/typo_substitution): `shape` (rounded rects,
   circles — often several sharing one center point to nest, e.g. concentric
   governance rings labeled "BOARD"/"AUDIT"/"SOC"), `decorator` (thin accent
   bars), `line`, and `gradient_overlay` (CSS `linear-gradient(...)` strings) show
   up routinely, with CSS-ish loose field names (`fill` vs `color`, `radius` vs
   `border_radius`, `"2px solid rgba(...)"` border shorthand). `premium_pdf.html`
   only had branches for the original 3 types too — this silently dropped
   decorations in the **already-shipped, already-in-production** premium PDF
   path, not just PPTX.

**Fix shipped this session**:
- `render_agent.py`: PPTX branch now reads the real `canvas_elements` from
  `planning_json`; premium-PDF branch now forwards `planning_json` into
  `ContentManifestSlide` so `PremiumVisualAgent` actually sees it.
- `painter.py`: `paint_custom_canvas()` rewritten to handle `shape`, `decorator`,
  `line`, `gradient_overlay` (plus the original 3), each parsed defensively via new
  `parse_canvas_color`/`parse_canvas_border`/`parse_css_linear_gradient` helpers
  (CSS-shorthand → python-pptx primitives) and each in its own `try/except` so one
  malformed element never blanks the rest of the slide.
- `premium_pdf.html`: the same 4 new types added as one shared Jinja macro
  (`render_canvas_element`) called from all 3 `pattern_type` branches, replacing
  the 3x-duplicated inline block that caused this exact class of drift.
- **Incidental bug fixed along the way**: `shape.fill.transparency = X`
  (python-pptx) is not a real API — it silently creates a dangling Python
  attribute with zero effect on the XML. Confirmed by dumping the shape's XML
  after "setting" it: no `<a:alpha>` anywhere, fully opaque regardless of the
  value. Every existing `transparency=` caller in `painter.py` (footer contrast
  bands, quote/hero backing panels) was rendering fully opaque this whole time.
  Fixed with a real `<a:alpha>` XML injection helper (`apply_fill_alpha`), which
  `add_rect()` now uses — a project-wide visual fix, not scoped to custom_canvas.
- Regression tests: `tests/test_painter_canvas_elements.py`,
  `tests/test_premium_pdf_canvas_elements.py`,
  `tests/test_render_agent_canvas_elements_wiring.py`.

**Evidence**: re-rendered deck D's already-generated content (no new LLM spend) —
the cover slide now shows a photo + gradient tint + accent line + person cutout +
title/subtitle instead of a blank panel; a roadmap slide shows 3 real phase cards
with a supporting photo; a governance slide shows genuinely concentric circles
labeled BOARD/AUDIT/SOC with layered transparency, matching what the Art Director
actually specified.

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

### Finding 4 — Premium PDF path: an unimplemented pattern survives from stale legacy data [FIXED]

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

**Fix shipped this session**: registered a data alignment
(`premium_pattern_whitelist_realign_v1` in
`services/core/data_alignment_service.py`) that re-filters every
`BrandPremiumVisualPattern.patterns_json` row against the current
`implemented_premium_patterns` whitelist, updating `patterns_json` and
`pattern_summary` when anything gets dropped. Idempotent (a re-run reports
`already_clean`, no writes), no LLM spend, follows the project's existing
`ALIGNMENT_REGISTRY` contract. Regression tests:
`tests/test_data_alignments.py::TestPremiumPatternWhitelistRealign` (drop,
idempotency, empty `patterns_json`, already-clean row all covered). Runs
automatically on next boot via the existing dispatch mechanism — no manual step.

## Quick wins (no design needed — ready for a PM to schedule)

1. ~~Extend `GRAMMAR_TO_ARTISTIC_PDF` with the 4 missing `composition_*` keys~~ —
   done (Finding 2).
2. ~~Register a data alignment for stale premium pattern data~~ — done (Finding 4).
3. ~~Build the real `canvas_elements` builder for `custom_canvas`~~ — done (Finding 1b).
4. **PPTX path's `layout_slug=None` fallback** (`render_agent.py`, ~10-20% of
   slides where the Analyst call didn't set a slug) reads
   `content_json["layout_type"]` — the Outline's `composition_*` vocabulary — and
   feeds it straight to `GRAMMAR_TO_PAINTER`, which has no bare `composition_*`
   keys either (only the values these keys map *to*). Smaller than Finding 1
   (fewer slides hit this path) but the same bug shape; worth a one-line
   `GRAMMAR_TO_PAINTER` addition (`composition_hero`→itself, etc.) the next time
   this file is touched. **Still open — bumped up in priority**: Finding 5's
   diversity fix makes the Analyst/Art Director actively try to spread across all
   5 layouts, but this gap silently flattens some of that effort back into
   `composition_split` whenever no override is returned. Fixing Finding 5 without
   this one leaves real diversification effort partially wasted at render time.

## Acceptance criteria

### Phase 1 — Vocabulary fixes and the real canvas_elements builder (done)

- [x] `GRAMMAR_TO_PAINTER` recognizes all 5 values `prompt_analyst_v3` can emit,
      each mapping to a distinct, real `GammaPainter`-dispatchable value —
      `custom_canvas` included, now that it has real content to paint.
      (`tests/test_painter_bridge_grammar_mapping.py`)
- [x] The legacy PDF slide dict forwards `metrics`/`section_label`/`subtitle`.
      (`tests/test_render_agent_legacy_pdf_metrics.py`)
- [x] `GRAMMAR_TO_ARTISTIC_PDF` recognizes the Outline Generator's `composition_*`
      vocabulary (Finding 2) — parametrized test covering all 5 outline
      `layout_type` values, each resolving to a distinct legacy PDF `layout`.
      (`tests/test_artistic_pdf_legacy_layout.py::TestGrammarToArtisticPdfRecognizesOutlineVocabulary`)
- [x] A registered data alignment re-normalizes every `BrandPremiumVisualPattern`
      row against `implemented_premium_patterns` (Finding 4).
      (`tests/test_data_alignments.py::TestPremiumPatternWhitelistRealign`)
- [x] `canvas_elements` (Art Director output) reaches both renderers — PPTX via
      `render_agent.py` reading `planning_json` directly, premium PDF via
      `ContentManifestSlide.planning_json` actually being populated (Finding 1b).
      (`tests/test_render_agent_canvas_elements_wiring.py`)
- [x] `paint_custom_canvas()` and `premium_pdf.html` both render `shape`,
      `decorator`, `line`, `gradient_overlay` in addition to the original
      text/image/typo_substitution — one shared Jinja macro for the HTML side,
      one dispatch table for the PPTX side, neither able to drift from the other
      silently again. (`tests/test_painter_canvas_elements.py`,
      `tests/test_premium_pdf_canvas_elements.py`)

### Phase 2 — Re-measure before committing to Lever 1

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

- Lever 1 (Brand Grammar Mining) — explicitly deferred to Phase 2's re-measurement;
  not designed here.
- Any change to `prompt_analyst_v3`'s non-vocabulary instructions (the no-text/
  no-diagram photography rules) — untouched, not implicated by this session's
  findings.
- Radial gradients, N-stop (>2) linear gradients, and per-element `blend_mode`/
  CSS `filter` on `canvas_elements` — real production output hasn't produced these
  yet; `parse_css_linear_gradient` degrades unsupported gradient syntax to "skip"
  rather than guessing, and image `style`/`blend_mode` fields are ignored by the
  PPTX renderer (CSS-only concepts, no python-pptx equivalent attempted).
- A second real brand for a broader Lever-1 assessment — this session ran on Tesco
  only (the only fully-ingested brand available); see
  `docs/designs/synthesis-studio-v2-assessment.md` for that open item.

## Open questions

- [Architect] Whether to still pursue Option (b) from Finding 2 (unify the Outline
  Generator onto the canonical `GRAMMAR_GEOMETRIES` vocabulary project-wide) now
  that the surgical fix is live — would also close Quick Win 4 (the PPTX
  `layout_slug=None` fallback) in one move, at the cost of an LLM prompt change
  needing its own AI Architect validation.
- [Luis] Whether to schedule Phase 2's re-measurement session now or batch it with
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
  (`get_slide_visual_strategy`), `utils/seed.py` (`prompt_analyst_v3`,
  `prompt_art_director_v3`), `services/generation/art_director_service.py`
  (`plan_presentation_design` — where `canvas_elements` is produced),
  `services/rendering/premium_visual_agent.py` (`_load_patterns`,
  `get_latest_brand_patterns`, `_build_slides`), `services/rendering/painter.py`
  (`paint_custom_canvas`, `apply_fill_alpha`, `parse_canvas_color`,
  `parse_canvas_border`, `parse_css_linear_gradient`),
  `templates/premium_pdf.html` (`render_canvas_element` macro),
  `services/core/data_alignment_service.py`
  (`premium_pattern_whitelist_realign_v1`)
- `docs/ai/contracts/deck-layout-diversity-adr.md` — live validation of
  `prompt_analyst_v4`/`prompt_art_director_v4` (Finding 5)
- Tests added this session: `tests/test_painter_bridge_grammar_mapping.py`,
  `tests/test_render_agent_legacy_pdf_metrics.py`,
  `tests/test_artistic_pdf_legacy_layout.py::TestGrammarToArtisticPdfRecognizesOutlineVocabulary`,
  `tests/test_data_alignments.py::TestPremiumPatternWhitelistRealign`,
  `tests/test_painter_canvas_elements.py`,
  `tests/test_premium_pdf_canvas_elements.py`,
  `tests/test_render_agent_canvas_elements_wiring.py`,
  `tests/test_analyst_layout_diversity.py`
