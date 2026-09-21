# Spec: Artistic Generation Engine v2 (Brand Grammar Mining)

**Date**: 2026-09-21
**Requested by**: Luis
**Status**: Approved — Architect design + PM task breakdown done; ready for Backend Dev to start Phase 0
**Project**: GuepardAI

## Problem

The classic pipeline (`analyst_service.get_slide_visual_strategy()` → `ComposeLayoutTool`)
picks a `grammar_type` label from a fixed enum (`hero | split | data_grid | pillars |
custom_canvas`) per slide. It selects a layout; it never composes one. After
`docs/specs/synthesis-studio-v2.md`'s six fixes the output is now internally consistent
and genuinely varied, but still structurally generic — every brand's deck reduces to the
same five shapes. Tools like Gamma/NotebookLM treat layout as a continuous design space
generated from content; this system treats it as a lookup table.

Four new reference decks (`GuepardAI/Insumos/`) — two Tesco retail decks, a Coca-Cola
Embonor corporate deck with a strong, idiosyncratic visual system (photo-strip cover
banner, ribbon-style title band, custom donut-with-bottle-icon KPI charts), and a
heavily-illustrated Harry Potter/DC entertainment template — make it possible to test a
different approach: mine a brand's *own* compositional patterns from its real materials
and let generation compose directly in that brand's visual language, instead of
generating against Guepard's generic five-slug grammar. This is Lever 1 from
`docs/designs/synthesis-studio-v2-assessment.md` (2026-07-08), deferred until vocabulary
bugs were fixed and until enough distinct source material existed to avoid overfitting
to one brand's style. Both conditions are now met.

This spec formalizes `docs/designs/artistic-generation-v2.md` (committed 2026-09-21,
`9857960`) into a data model, tool contracts, and per-phase acceptance criteria an
Architect can design from and QA can validate against.

## Solution summary

Add an isolated second generation engine, selected per job via a new
`GenerationJob.engine_version` column (`"v1"` default, unchanged; `"v2_artistic"` new).
A new ingestion step mines named, geometry-based layout signatures from a brand's real
source decks (`BrandLayoutGrammar`, new table) by reusing Template Merge v2's shape
analyzer for traversal and adding an LLM clustering/naming pass. A new agent tool
(`ComposeCanvasTool`) replaces the visual-strategy-and-layout-selection step for
`v2_artistic` jobs only — it reasons directly in `canvas_elements` space (the free-form
primitive already fully built for `custom_canvas` — Synthesis Studio v2 Finding 1b),
informed by the brand's mined signatures as few-shot exemplars, and reuses today's
Redactor for content and today's two renderers (`paint_custom_canvas()`,
`premium_pdf.html`) for output unchanged. `v1` jobs never call any new code path.

## Users and roles

- **Cliente/Admin** (existing roles) — opts a brand and a generation job into the v2
  engine from an explicitly separate, isolated UI entry point (Phase 4); default
  generation flow is unaffected and stays on v1.
- **Superadmin** — triggers grammar mining (Phase 0) per brand; this is not part of the
  normal `/api/brand/upload` flow, since it is exploratory and initially scoped to the
  four Insumos brands, not every brand automatically.
- **Architect / AI Architect / PM / Backend Dev / Senior Reviewer / QA** — same review
  chain as every other feature per `CLAUDE.md`; the AI Architect gate is explicitly
  mandatory before Phase 1 is implemented (new LLM touchpoint) and before Phase 3's
  QA-judge bias audit is trusted.

## Data model

### New table: `BrandLayoutGrammar`

Mirrors the precedent already set by `BrandPremiumVisualPattern` ("Keeps executable
visual patterns separate from `BrandVisualDna` so the [existing] pipeline can continue
using its existing brand DNA contract") — mined grammar is a variable-length collection
of structured signatures, not the scalar/simple fields `BrandVisualDna` holds, so it gets
its own table rather than an extension.

```python
class BrandLayoutGrammar(Base):
    __tablename__ = "brand_layout_grammar"

    id               = Column(Integer, primary_key=True, index=True)
    brand_id         = Column(Integer, ForeignKey("brands.id"), index=True)
    source_filename  = Column(String, index=True, nullable=False)  # which Insumos file this was mined from

    signatures_json  = Column(JSONB, nullable=True)   # list[LayoutSignature], see below
    mining_summary   = Column(Text, nullable=True)     # human-readable notes from the mining LLM call
    raw_extraction   = Column(JSONB, nullable=True)    # pre-clustering analyzer output, audit trail

    created_at       = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
```

One row per `(brand_id, source_filename)`, same granularity as `BrandVisualDna` and
`BrandPremiumVisualPattern` today.

### `LayoutSignature` shape (element of `signatures_json`)

```json
{
  "name": "donut-kpi-trio",
  "source_slide_indices": [4, 9, 14],
  "content_shape": "metric_comparison",
  "slots": [
    {"role": "icon_center", "x_pct": 42.0, "y_pct": 30.0, "w_pct": 16.0, "h_pct": 16.0},
    {"role": "value_label", "x_pct": 42.0, "y_pct": 48.0, "w_pct": 16.0, "h_pct": 6.0}
  ],
  "motifs": ["brand_icon_center", "ribbon_band"],
  "confidence": 0.78
}
```

- `content_shape` reuses the same content-classification vocabulary the Analyst already
  produces today (metric-heavy / narrative / quote / cover) — not reinvented.
- `slots` are percentages of slide width/height, **not EMU** — this is a deliberate
  choice, not a simplification: `canvas_elements` (`painter.py`'s `self.w()`/`self.h()`
  scalers, `premium_pdf.html`'s macro) already consume `x`/`y`/`w`/`h` as 0-100
  percentages. Storing signatures in the same coordinate space means `ComposeCanvasTool`
  can pass a mined slot straight into a `canvas_elements` few-shot exemplar with zero
  conversion.
- `motifs` is an open, growing tag vocabulary (not a closed enum) — Phase 0 seeds it from
  what mining actually finds across the 4 samples; it is not pre-designed here.

### `IngestionJob.ingestion_type` gets a fourth value

Current valid values (`models.py:292`): `'visual_dna' | 'artistic' | 'knowledge'`. Add
`'layout_grammar'` — triggered explicitly per brand (Phase 0), never as part of the
default `/api/brand/upload` flow, since mining is exploratory/expensive and initially
scoped to the four Insumos brands only.

## New tool contracts

### `MineLayoutGrammarTool` (`BaseAgentTool` subclass, ingestion-side)

```python
class MineLayoutGrammarArgs(BaseModel):
    brand_id: int = Field(...)
    source_filename: str = Field(...)
    slide_profiles: List[dict] = Field(...)  # deterministic analyzer output, pre-clustering

class MineLayoutGrammarTool(BaseAgentTool):
    name = "mine_layout_grammar"
    description = "Clusters analyzer slide profiles into named, reusable layout signatures."
    args_schema = MineLayoutGrammarArgs
```

- The deterministic half (shape traversal, per-slot geometry) is **not** a `BaseAgentTool`
  call — it's a plain extension of `template_traversal.py`/`template_analyzer.py`
  (same convention as those modules today: no LLM, no tool wrapper needed). The PDF path
  (Embonor) needs new extraction work here — PDFs have no shape XML, so this is
  image+text-region detection, not a trivial extension of the PPTX traversal; scope this
  explicitly as new code in Phase 0, not an assumed reuse.
- `MineLayoutGrammarTool` is only the LLM-calling half: given the deterministic geometry
  clusters, it names each cluster, assigns `content_shape` and `motifs`, and writes
  `BrandLayoutGrammar`. Calls `generate_json(..., specialization="design")` (Phase 1's
  composer and this tool are the only two new LLM touchpoints in this spec). Must call
  `self.log_decision()` — this is a real AI decision (naming/classifying a visual
  pattern), not a deterministic step.

### `ComposeCanvasTool` (`BaseAgentTool` subclass, generation-side)

```python
class ComposeCanvasArgs(BaseModel):
    job_id: int = Field(...)
    slide_id: int = Field(...)       # PresentationSlide already content_ready (Redactor already ran)
    brand_id: int = Field(...)

class ComposeCanvasTool(BaseAgentTool):
    name = "compose_canvas"
    description = "Designs a slide directly in canvas_elements space, informed by the brand's mined layout grammar."
    args_schema = ComposeCanvasArgs
```

- Replaces `analyst_service.get_slide_visual_strategy()` + `ComposeLayoutTool` for
  `engine_version="v2_artistic"` jobs only — **not** the Redactor. Content synthesis
  (`GenerateTextTool`) runs exactly as it does in v1; `ComposeCanvasTool` consumes the
  already-written slide content and decides composition only.
- Reads the slide's `content_shape` (already produced by the Redactor's content
  synthesis today, reused not rebuilt) and the brand's `BrandLayoutGrammar` rows,
  selects the most relevant signature(s) as few-shot exemplars, and prompts a new
  versioned key `prompt_compose_canvas_v1` (seeded in `utils/seed.py`, following the
  project's prompt-versioning convention — never edits an existing `prompt_*` key).
- Calls `providers.llm_provider.generate_premium_json()` — **not**
  `generate_json(..., specialization="design")`, which is confirmed dead code for
  routing purposes (`docs/ai/contracts/deck-design-brief-adr.md`). Live-validated,
  single call, in `docs/ai/contracts/artistic-generation-v2-adr.md`: one call is
  sufficient to produce a complete, on-contract `canvas_elements` list — resolves the
  design doc's "one call vs. two" open question.
- The prompt **must enumerate the exact per-type field names** `paint_custom_canvas()`
  and `render_canvas_element()` read (`path`/`size`/`weight`/`content`, not a
  paraphrase) — live-validated proof that an unconstrained schema description
  produces confident, valid, but silently off-contract JSON (see the ADR's Round 1).
  Must also explicitly forbid inventing `image`/icon sources: no icon glyph library
  exists in this system; the validated fallback is representing motifs with `shape`
  primitives only.
- Writes its result directly to `PresentationSlide.planning_json["art_director"]
  ["canvas_elements"]` (the exact field `render_agent.py` and `premium_pdf.html`
  already read per Finding 1b) and unconditionally sets `layout_slug="custom_canvas"`.
  This is why Phase 2 needs almost no renderer work to start: every v2 slide is a
  `custom_canvas` slide from the renderer's point of view, and that path is already
  fully built.
- Must call `self.log_decision()` for every slide — this is the single most consequential
  AI decision in the v2 pipeline and needs the same audit trail as `ComposeLayoutTool`
  has today.

### Orchestrator routing

`AgentOrchestrator.run_design_and_render()` (`agents/orchestrator.py:372`) branches on
`job.engine_version` immediately before its existing `self.compose_layout(...)` call
(`agents/orchestrator.py:394`): `"v1"` (or unset — existing jobs have no value in this
new column) calls `self.compose_layout` exactly as today, unmodified; `"v2_artistic"`
calls `self.compose_canvas` (new `ComposeCanvasTool` instance) instead. No other line in
`run_generation_pipeline()`, `run_design_and_render()`, `analyst_service.py`, or
`art_director_service.py` changes. This branch is the entire integration surface between
v1 and v2 — everything else in this spec is new code reached only from the
`"v2_artistic"` arm.

## Acceptance criteria

**Phase 0 — Mining**
- [ ] `analyze_template()` (or a documented PDF-path equivalent) runs successfully over
      all 4 Insumos samples except the Harry Potter `.mp4` files, which are skipped
      without raising.
- [ ] `MineLayoutGrammarTool` produces at least 3 named, distinct `LayoutSignature`
      entries for the Embonor brand, including one that captures the donut-with-icon KPI
      pattern (verified by a human reviewer reading `signatures_json`, not just that the
      row exists).
- [ ] `BrandLayoutGrammar` rows are created for all 4 samples; `PPT_Template_Core.pptx`
      is inventoried during this phase (not before), per the design doc.
- [ ] Adding `'layout_grammar'` to `IngestionJob.ingestion_type` does not change behavior
      for any existing `'visual_dna' | 'artistic' | 'knowledge'` job (regression test).

**Phase 1 — Composer**
- [x] AI Architect live-validation ADR exists in `docs/ai/contracts/` for the composer
      touchpoint before this phase is implemented — done:
      `docs/ai/contracts/artistic-generation-v2-adr.md` (2026-09-21). Channel decided
      (`generate_premium_json()`), one-call shape confirmed sufficient, exact field
      vocabulary validated against both renderers.
- [ ] `prompt_compose_canvas_v1` (implementation) enumerates the per-type field names
      literally, per the ADR's Round 1 finding — a schema described only conceptually
      is not acceptable, it must be tested to reproduce the ADR's Round 2 result
      (zero off-contract keys) before this criterion is met.
- [ ] Given a metric-heavy slide and Embonor's mined grammar, `ComposeCanvasTool`'s
      output `canvas_elements` includes at least one element referencing the mined
      donut/icon-center pattern (not a generic bar/card layout) — spot-checked visually,
      not just schema-validated.
- [ ] `ComposeCanvasTool` never runs for `engine_version="v1"` jobs (unit test on the
      orchestrator branch).
- [ ] Every `ComposeCanvasTool` call writes an `ArtDirectorDecision` row via
      `self.log_decision()`.

**Phase 2 — Rendering**
- [ ] Any new `canvas_elements` element type Phase 0 surfaces (e.g. donut-with-icon,
      photo-strip band) is added to `paint_custom_canvas()` and `premium_pdf.html`'s
      `render_canvas_element()` macro, each in its own try/except (matching the existing
      Finding 1b dispatch pattern) — driven by what mining actually found, not spec'd
      speculatively here.
- [ ] No existing element type's rendering (`text`/`image`/`typo_substitution`/
      `shape`/`decorator`/`line`/`gradient_overlay`) changes behavior for v1 jobs.
- [ ] `premium_pdf.html`'s `render_canvas_element` macro gains `text-align` support
      (found missing entirely while validating Touchpoint B — `painter.py`'s PPTX path
      already supports left/center via `align`; the two renderers must not silently
      diverge on the same `canvas_elements` payload).

**Phase 3 — QA bias audit**
- [x] Live audit run, 2026-09-21 — bias **confirmed**, not merely checked:
      `docs/ai/contracts/artistic-generation-v2-adr.md`. Identical brand/image signals,
      only composition description varied: "safe grid" scored 0.95, "bold asymmetric"
      scored 0.68, with the judge's own reasoning citing boldness itself as a brand-fit
      penalty. Also found structurally: `ScoreFidelityTool`'s `slides_context` never
      includes `canvas_elements` at all — the judge is composition-blind, v1 and v2 alike.
- [ ] A versioned `prompt_score_fidelity_v2_artistic` ships as a **Phase 1 prerequisite**
      (not a parallel/lagging workstream) for any `v2_artistic` job that isn't a
      manually-reviewed pilot batch — never an in-place edit of the v1 judge prompt.
- [ ] `ScoreFidelityTool`'s `slides_context` builder is extended, for `v2_artistic`
      jobs only, to summarize `canvas_elements` (element count/type mix; any element
      whose `x + w` or `y + h` exceeds 100 — a real geometry defect) — a reworded
      prompt alone doesn't fix a judge that never receives the geometry it's meant to
      evaluate.

**Phase 4 — Rollout**
- [ ] A `v2_artistic` job is reachable only from an explicitly separate nav
      entry/route — no shared component is edited in place to "become" v2.
- [ ] Batch generation lets Luis compare v1 vs. v2 output for the same prompt/brand
      side by side before any promote/retire decision.
- [ ] Full existing backend test suite (`pytest tests/`) passes unmodified after the
      `engine_version` column is added — proves the isolation constraint held.

## Edge cases and error scenarios

- **A brand has no `BrandLayoutGrammar` row** (mining never run) but a job requests
  `engine_version="v2_artistic"` for it → `ComposeCanvasTool` must fail loudly with a
  clear `GenerationJob.status = ERROR` message ("brand has no mined layout grammar"),
  never silently fall back to v1's grammar enum — a silent fallback would defeat the
  isolation constraint by quietly reintroducing a v1 code path into v2's execution.
- **PDF mining (Embonor) finds zero extractable shape-equivalent regions** on a page
  (e.g. a full-bleed photo with no text) → that page contributes no `LayoutSignature`
  and is logged, not treated as a mining failure.
- **`ComposeCanvasTool` returns malformed or empty `canvas_elements`** → same QA
  rejection path `ScoreFidelityTool`/deterministic validation already uses for v1
  malformed output; no new error-handling code path needed here.
- **A `v1` job's `engine_version` column is `NULL`** (every job created before this
  migration) → orchestrator branch treats `NULL` identically to `"v1"` (explicit
  `!= "v2_artistic"` check, not a `== "v1"` check) — never require a backfill.
- **Repeated mining of the same `(brand_id, source_filename)`** → idempotent: re-running
  `MineLayoutGrammarTool` replaces (not duplicates) that brand/file's
  `BrandLayoutGrammar` row, matching `BrandVisualDna`/`BrandPremiumVisualPattern`'s
  existing re-ingestion behavior.

## Out of scope

- Touching `AgentOrchestrator`'s existing methods, `analyst_service.py`,
  `art_director_service.py`, or `painter.py` for `engine_version="v1"` jobs — the whole
  point of the isolation constraint (Luis, 2026-09-21).
- Video ingestion (Harry Potter sample's `.mp4` files) — explicit non-goal.
- ~~Resolving whether `ComposeCanvasTool` is one LLM call or two~~ — resolved by live
  validation: one call (`docs/ai/contracts/artistic-generation-v2-adr.md`).
- Mining `PPT_Template_Core.pptx` before Phase 0 — inventory happens during Phase 0, not
  before.
- Any change to `PresentationReview`/rating, portfolio management, or auth/tenancy —
  unrelated surfaces.
- Automatic mining for brands outside the four Insumos samples — Phase 0 is scoped to
  those four; extending mining to all brands is a future decision, not this spec's.

## Open questions

- [Luis] Any additional reference decks worth adding before Phase 0 starts?
  (Carried over from the design doc, still unanswered.)
- [Architect] Exact PDF shape-equivalent extraction approach for the Embonor sample
  (image+text-region detection library choice) — not resolved here; flagged in the
  design doc as "new work, not an assumed extension."
- [Architect] How to sequence Phase 3's now-confirmed judge-bias fix relative to
  Phase 1 implementation start — the ADR recommends treating it as a Phase 1
  prerequisite (at minimum for anything beyond a manually-reviewed pilot batch), which
  changes the design doc's original "Phases run in AI-Architect-then-implement order
  but aren't otherwise blocking" framing. Needs an explicit Architect call, not an
  Analyst one.

Resolved by AI Architect live validation (`docs/ai/contracts/artistic-generation-v2-adr.md`,
2026-09-21) — no longer open:
- Composer provider/channel: `generate_premium_json()`, not `specialization="design"`.
- One composer call vs. two: one call, validated sufficient.
- Mining touchpoint provider: `generate_json(..., specialization="general")` — no
  premium channel needed for classification.
- QA judge bias: confirmed (not merely a risk), with a measured example (0.95 vs 0.68
  for identical signals, differing only in composition boldness described in text).

## References

- `docs/designs/artistic-generation-v2.md` — the design doc this spec formalizes
- `docs/designs/synthesis-studio-v2-assessment.md` — Lever 1's original framing
- `docs/specs/synthesis-studio-v2.md` — Finding 1b (`canvas_elements` builder this reuses
  wholesale for rendering)
- `backend/services/templates/template_traversal.py`,
  `backend/services/templates/template_analyzer.py` — reused deterministic analyzer
- `backend/services/rendering/painter.py` (`paint_custom_canvas`),
  `backend/templates/premium_pdf.html` (`render_canvas_element` macro) — reused renderers
- `backend/models.py` — `BrandVisualDna` (:133), `BrandPremiumVisualPattern` (:270,
  precedent for keeping derived visual data in its own table), `GenerationJob` (:312),
  `IngestionJob` (:294)
- `backend/agents/orchestrator.py` — `run_design_and_render()` (:372), the exact
  integration point for `engine_version` routing
- `GuepardAI/Insumos/` — the 4 reference files
- `docs/ai/contracts/artistic-generation-v2-adr.md` — AI Architect live validation of
  both new touchpoints plus the Phase 3 QA bias audit (2026-09-21)

---

## Architect decision (2026-09-21)

Resolves the two `[Architect]`-tagged open questions above, using the AI Architect's
ADR as input. Design/data model/tool contracts above stand as written by the Analyst —
nothing here changes them.

### PDF shape-equivalent extraction (Phase 0)

Extend, don't invent: `services/ingestion/visual_dna_service.py::extract_pdf_dna()`
already opens a PDF with `fitz` (PyMuPDF — already a project dependency,
`requirements.txt:22`, already imported in 4 service files) and walks
`page.get_text("dict")["blocks"]` for font/color extraction. Phase 0's PDF path reuses
the exact same primitives, extended to capture geometry:

- **Text regions**: `page.get_text("dict")["blocks"]` — each block already carries a
  `bbox` (x0/y0/x1/y1 in PDF points, real geometry PyMuPDF provides for free, unused by
  `extract_pdf_dna()` today since it only needed font/color, not position). Normalize to
  page-width/height percentages and classify role with the same heuristics
  `template_analyzer.py::_infer_role()` already uses (top-fraction → title,
  small-area → footnote) — reused, not reimplemented per-format.
- **Image regions**: `page.get_image_rects(xref)` per entry from `page.get_images(full=True)`
  — real per-image bbox. Note: `extract_pdf_dna()`'s existing image extraction ("BULLETPROOF
  XREF EXTRACTION") only needs image *presence* for the asset library today; mining needs
  *geometry*, so this is genuinely new code alongside the existing function, not a copy of it.
- **Vector/decorative regions** (the ribbon band, donut-ring strokes Embonor's deck
  actually uses): `page.get_drawings()` — returns each vector path's `rect` and
  fill/stroke color. Filter near-invisible fills with the existing `_is_neutral()`
  helper to avoid anti-aliasing noise.
- New function: `services/templates/template_analyzer.py::analyze_pdf_template(pdf_path,
  config)`, returning the same `SlideProfile`-shaped structure the PPTX path already
  produces (or a `PageProfile` sibling dataclass if `SlideProfile`'s PPTX-only fields
  don't fit cleanly — Backend Dev's call at implementation time, not fixed here) so
  `MineLayoutGrammarTool` consumes one uniform shape regardless of source format, never
  branching on file type downstream of Phase 0.
- No new dependency, no new library research needed — this was the open risk in the
  design doc ("new work, not an assumed extension"); it's now scoped to extending an
  already-proven, already-imported library along a pattern this codebase already runs
  in production ingestion.

### Phase 3 sequencing relative to Phase 1

`ComposeCanvasTool` (`agents/compose_canvas.py`, new) and the judge fix
(`agents/qa_validator.py` + a new `prompt_score_fidelity_v2_artistic` in `utils/seed.py`)
touch disjoint files — PM may schedule them **in parallel** (different Backend Devs, if
capacity allows) or sequentially; either is fine for implementation order.

The one hard gate, per the AI Architect's escalation: `engine_version="v2_artistic"`
must not reach real batch/rollout usage (Phase 4) until both the versioned judge
prompt AND the `slides_context` `canvas_elements` summary (element count/type mix,
out-of-bounds geometry check) are merged and validated — a reworded prompt alone,
without the geometry actually reaching the judge, doesn't close the finding. A
manually-reviewed pilot (Luis reviewing a handful of decks directly, QA's automatic
retry score not the acceptance signal) is fine before that gate — same shape as
Synthesis Studio v2's own elicitation method, already proven in this project.

## PM task breakdown

Sequencing: Phase 0 first (nothing downstream has real data without it). Phase 1 and
Phase 3 can run in parallel once Phase 0 produces at least one brand's
`BrandLayoutGrammar`. Phase 2 follows Phase 1 (needs real composer output to know what
new element types, if any, are actually missing). Phase 4 is gated on Phase 1 + Phase 3
both landing, per the Architect decision above.

**Phase 0 — Backend Dev**
- [ ] `BrandLayoutGrammar` model + `IngestionJob.ingestion_type` gains `'layout_grammar'`
- [ ] `analyze_pdf_template()` in `template_analyzer.py` (PDF geometry extraction, per
      Architect decision above)
- [ ] `MineLayoutGrammarTool` (`BaseAgentTool`, `generate_json(specialization="general")`)
- [ ] Run mining over all 4 Insumos brands; inventory `PPT_Template_Core.pptx`
- [ ] Regression test: `'layout_grammar'` addition doesn't affect existing ingestion types

**Phase 1 — Backend Dev**
- [ ] `GenerationJob.engine_version` column (default `NULL`/`"v1"`)
- [ ] `ComposeCanvasTool` (`BaseAgentTool`, `generate_premium_json()`), prompt
      `prompt_compose_canvas_v1` with the literal field vocabulary from the ADR
- [ ] Orchestrator branch in `run_design_and_render()` (`agents/orchestrator.py:372`)
- [ ] Unit test: `ComposeCanvasTool` never invoked for `v1`/`NULL` jobs

**Phase 2 — Backend Dev** (after Phase 1 produces real output)
- [ ] Add any new element type(s) Phase 0/1 actually surfaced to `paint_custom_canvas()`
      and `render_canvas_element()`
- [ ] Fix `premium_pdf.html` canvas-text alignment gap (found during ADR validation)

**Phase 3 — Backend Dev** (parallel with Phase 1, per Architect decision)
- [ ] `prompt_score_fidelity_v2_artistic` (new versioned key, `utils/seed.py`)
- [ ] Extend `ScoreFidelityTool`'s `slides_context` builder with a `canvas_elements`
      summary for `v2_artistic` jobs
- [ ] Re-run the ADR's bias test against the new prompt; confirm the score gap closes

**Phase 4 — Frontend Dev + Backend Dev** (gated on Phase 1 + Phase 3)
- [ ] Isolated nav entry/route for `v2_artistic` generation
- [ ] Batch generation UI for v1-vs-v2 side-by-side comparison

**Tech Writer** — architecture doc update (`docs/architecture/GuepardAI-overview.md`)
once Phase 1 lands; runs in parallel with dev work per standing convention.

Next: Backend Dev starts Phase 0 (and, in parallel where capacity allows, Phase 3);
Senior Reviewer review happens per-phase as each lands, not held for the whole feature.
