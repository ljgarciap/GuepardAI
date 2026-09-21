# Design: Artistic Generation Engine v2 (Brand Grammar Mining)

**Date**: 2026-09-21
**Requested by**: Luis
**Status**: Draft — plan proposed, awaiting Luis's go-ahead before an Analyst spec is written
**Project**: GuepardAI
**Origin**: `docs/designs/synthesis-studio-v2-assessment.md` (2026-07-08, Lever 1) +
`docs/specs/synthesis-studio-v2.md` (2026-09-20/21, Phase 1/2 findings) — this is the
"expensive lever" both documents deferred until vocabulary/wiring bugs were fixed and
re-measured. That re-measurement is done; this is the next step.

---

## Problem

The classic pipeline's layout vocabulary is a **fixed enum** (`hero | split | data_grid
| pillars | custom_canvas`, ~5-8 real painter methods with hardcoded Python geometry).
Two LLM calls (Analyst, Art Director) *select a label* from that enum per slide — they
never *compose a page*. This produces output that is internally consistent and now
(after `synthesis-studio-v2.md`'s 6 fixes) genuinely varied, but structurally generic —
"5 PowerPoint templates," not a brand's own visual language. Tools like Gamma/NotebookLM
treat layout as a continuous design space generated per content; we treat it as a lookup
table. Closing that gap requires the brand's *own* compositional system to inform
generation, not Guepard's generic grammar — Lever 1 from the July assessment.

New reference material makes this tractable now: 4 real decks with genuinely distinct
visual systems (retail/loyalty, corporate/financial with strong custom infographics,
and a heavily-illustrated entertainment-franchise style), vs. the single brand (Tesco)
available when Lever 1 was first deferred for lack of data.

## Non-negotiable constraint (Luis, 2026-09-21)

**This ships as a separate method — it must not touch or risk the existing pipeline.**
Same governing principle already approved for the Synthesis Studio v2 UI rollout
(assessment §5a): new engine, new route, `GenerationJob.engine_version` flag
(`"v1"` today's pipeline, unchanged; `"v2_artistic"` this work) routed at the
orchestrator level — never a fork or in-place edit of `AgentOrchestrator`,
`analyst_service.py`, `art_director_service.py`, or `painter.py`'s existing methods.
v1 stays exactly as it is, indefinitely, until/unless Luis decides otherwise.

## Reference material inventory (`GuepardAI/Insumos/`)

| File | Shape | Why it's useful here |
|---|---|---|
| `Tesco Style.pptx` / `Tesco Style_2.pptx` | 20 / 23 slides | Already ingested (`BrandVisualDna`/`BrandArtisticEssence` exist) — baseline, retail/loyalty tone |
| `201504_Presentacion-Corporativa-2015-Q4.pdf` | 27 pages (Coca-Cola Embonor) | **Strongest mining candidate**: real custom motifs no current `grammar_type` reproduces — a photo-strip/contact-sheet cover banner, a red ribbon-style title band, and KPI slides built from *custom circular icon-infused donut charts* (brand's bottle silhouette at the donut's center) instead of generic cards |
| `Harry Potter y DC template.pptx` | 31 slides, 892 MB, 302 media (150 png/97 jpeg/41 emf/5 svg/**3 mp4**) | Deliberately extreme test case — cinematic/editorial illustration density; also the one sample with embedded video, which forces an explicit out-of-scope decision (see below) rather than a silent gap |
| `PPT_Template_Core.pptx` | 51 slides | Not yet characterized — inventory during Phase 0, not before |

Ingesting all 4 (not just Tesco) is the point: a grammar-mining approach validated on
one brand risks overfitting to Tesco's specific style; a corporate-financial deck and
an entertainment-franchise deck are close to opposite ends of the visual spectrum on
purpose.

## Phased plan

### Phase 0 — Mine real layout grammar from the 4 samples (ingestion-side)

Extend, don't rebuild: Template Merge v2's analyzer (`services/templates/
template_traversal.py`, `template_analyzer.py`) already does shape traversal, per-slot
geometry, role inference, and typographic capacity — per the July assessment,
"~70% of the extraction work" needed here already exists. Phase 0 is:

1. Run the analyzer over all 4 samples (PDF path needs a page→shape-equivalent
   extraction step the PPTX path doesn't — likely image+text-region detection rather
   than true shape XML, since a PDF has no editable shape tree; scope this explicitly
   as new work, not an assumed extension).
2. Cluster per-slide slot profiles into **named, deduplicated layout signatures** per
   brand (e.g., Embonor's "banded-header-with-photo-strip", "donut-kpi-trio") instead
   of shoehorning them into the existing `GRAMMAR_GEOMETRIES` 10-slug vocabulary.
3. New storage: either a new table (`BrandLayoutGrammar`) or an extension of
   `BrandVisualDna` — decide in the Analyst spec, not here; whichever it is, it must
   carry real geometry (slot positions/proportions as %, not just a text description)
   so it's usable by a renderer, not just a prompt.
4. **Video out of scope for v1**: the Harry Potter sample's 3 `.mp4` files are not
   mined or referenced — static imagery and vector graphics only. Documented here so
   it's a decision, not a silent gap discovered later.

### Phase 1 — A composer that designs, not selects (generation-side)

New agent tool (name TBD in the Analyst spec, e.g. `ComposeCanvasTool`) that replaces
the Analyst+Art Director's "pick one of 5 labels" step for `engine_version="v2_artistic"`
jobs only. Every slide is effectively a `custom_canvas` decision from the start:
the LLM reasons directly in the `canvas_elements` space (already fully built —
`paint_custom_canvas()` and `premium_pdf.html`'s shared macro from
`docs/specs/synthesis-studio-v2.md` Finding 1b handle `shape`/`decorator`/`line`/
`gradient_overlay`/`text`/`image` today), informed by:

- The brand's **mined** grammar (Phase 0) as concrete few-shot exemplars — "this
  brand's own way of showing 3 KPIs is a donut-with-icon-center trio," not a generic
  instruction to "be creative."
- Content shape (metric-heavy / narrative / quote / cover), same signal the Analyst
  already extracts today, reused not rebuilt.

This is the one piece that must go through the **AI Architect gate** before
implementation (new touchpoint: different response schema than today's `grammar_type`
enum, likely a richer `canvas_elements`-shaped response from the first call rather than
a second-pass override).

### Phase 2 — Rendering: extend the existing builder, don't replace it

No new renderer needed as a starting point. `paint_custom_canvas()` (PPTX) and
`premium_pdf.html` already render the full current `canvas_elements` vocabulary.
Phase 0's mining will likely surface element *shapes* the current vocabulary doesn't
cover yet (e.g., a donut chart with an embedded brand icon, a photo-strip/contact-sheet
band) — add exactly those, driven by what mining actually finds repeated across the 4
samples, not speculative generality ahead of evidence.

### Phase 3 — QA: a rubric that doesn't penalize the thing we're asking for

Flagged already in this session's Architect review: today's `ScoreFidelityTool` judge
has never been audited for bias toward "safe" (grid-of-cards) vs. "bold" (asymmetric,
bleeding, non-rectangular) composition. Before trusting v2's QA loop:

- AI Architect runs the same ambitious `canvas_elements` output through the existing
  judge and inspects the score distribution and rejection reasons.
- If bias is confirmed, v2 gets its own judge rubric/prompt (versioned, same
  `prompt_*` convention) rather than inheriting v1's — never edit the v1 judge prompt
  in place, per standing project rule.

### Phase 4 — Rollout

Same shape already approved for Synthesis Studio v2's UI (assessment §5a, not
re-litigated here): isolated nav entry/route, batch-generation support so Luis can
compare v1 vs. v2 output across many decks before any promote/retire decision. No
shared component gets edited in place to "become" v2.

## Governance and sequencing

This is large enough to need the project's normal chain, not another same-session
shortcut:

1. **Analyst** writes `docs/specs/artistic-generation-v2.md` — formalizes the data
   model for mined grammar, the exact new tool contract (`BaseAgentTool` subclass,
   `args_schema`), and acceptance criteria per phase. This design doc is the input to
   that spec, not a replacement for it.
2. **AI Architect** validates Phase 1's new touchpoint (live `test-ai-request`, ADR)
   and runs Phase 3's judge-bias check, before Phase 1 is implemented.
3. **PM** breaks Phases 0-4 into tasks once the spec exists.
4. Explicitly **not** timeboxed to fit alongside other work — Luis confirmed the long
   path is acceptable here.

## Out of scope (this document)

- Touching `AgentOrchestrator`, `analyst_service.py`, `art_director_service.py`, or
  `painter.py`'s existing methods for `engine_version="v1"` jobs — never, this is the
  whole point of the isolation constraint.
- Video ingestion (the Harry Potter sample's `.mp4` files) — noted above, explicit
  non-goal for v1 of this initiative.
- Deciding the exact new DB schema (`BrandLayoutGrammar` vs. extending
  `BrandVisualDna`) — Analyst spec's job.
- `PPT_Template_Core.pptx` — not characterized yet; Phase 0 inventories it, this
  document doesn't presume what it contains.

## Open questions

- [Luis] Any additional reference decks worth adding before Phase 0 starts, now that
  the value of deliberately diverse samples is clear?
- [Analyst] Exact schema for mined grammar storage.
- [AI Architect] Whether Phase 1's composer is one call (canvas_elements directly) or
  two (a planning pass + a canvas_elements pass, mirroring today's Analyst→Art
  Director split) — a real design tradeoff, not decided here.

## References

- `docs/designs/synthesis-studio-v2-assessment.md` — Lever 1's original framing
- `docs/specs/synthesis-studio-v2.md` — Findings 1-5 + Quick Wins 1-4, the wiring and
  vocabulary fixes this design builds on top of (Finding 1b's canvas_elements builder
  in particular — Phase 2 here has almost nothing to build because of it)
- `services/templates/template_traversal.py`, `template_analyzer.py` — reused analyzer
- `services/rendering/painter.py` (`paint_custom_canvas`), `templates/premium_pdf.html`
  (`render_canvas_element` macro) — reused renderers
- `GuepardAI/Insumos/` — the 4 reference files inventoried above
