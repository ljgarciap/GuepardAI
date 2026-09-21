# ADR: Artistic Generation Engine v2 — Composer + Grammar Mining touchpoints, Phase 3 QA bias audit

**Date validated**: 2026-09-21 (live calls, no mocks — see Validation below)
**Validated by**: AI Architect
**Status**: VALIDATED WITH FINDINGS — Phase 1 may proceed with the corrected contract below; Phase 3's judge bias is CONFIRMED (not a risk to check later) and must be addressed before any `v2_artistic` job goes through the standard QA retry loop
**Used in**: `agents/compose_canvas.py` (`ComposeCanvasTool`, not yet implemented), `agents/mine_layout_grammar.py` (`MineLayoutGrammarTool`, not yet implemented), `agents/qa_validator.py` (`ScoreFidelityTool`, existing)
**Spec**: `docs/specs/artistic-generation-v2.md`

---

## Decision — Touchpoint B (`ComposeCanvasTool`)

Route through the existing `generate_premium_json()` channel (`providers/llm_provider.py`,
`claude-sonnet-4-5`, dedicated Anthropic path, its own audit log) — **not**
`generate_json(..., specialization="design")`. That path is confirmed dead code
(`docs/ai/contracts/deck-design-brief-adr.md`, Finding 2: `_generate_json_raw` never
calls `resolve_provider()`; `specialization` is accepted and logged but never changes
dispatch). `generate_premium_json()` is the only call in this codebase that reliably
reaches Claude today, and it's exactly what composing directly in `canvas_elements`
space needs — spatial/design reasoning, not classification. Zero new provider code.

## Validation — Touchpoint B (live, 2 rounds, `claude-sonnet-4-5`)

**Round 1** — schema drafted from the spec's prose alone (`source`, `font_size`,
`font_weight`, `alignment`, `fill_color`): call succeeded (22.49s), returned valid,
well-structured JSON — 15 elements, sensible spatial reuse of the mined
`donut-kpi-trio` signature. **But every field name was off-contract**: `paint_custom_canvas()`
(`painter.py`) reads `path`/`size`/`weight`/`content`, not `source`/`font_size`/
`font_weight`; `render_canvas_element()` (`premium_pdf.html`) agrees with `painter.py`,
not with round 1's schema. Shipping round 1's contract would have rendered every
element with silently wrong defaults (dropped font size, weight, alignment) rather than
erroring — the failure mode this whole AI Architect gate exists to catch before
implementation. It also invented `"source": "icon:trending_up"` / `"pie_chart"` /
`"star"` — semantic icon references that resolve to nothing; no icon glyph library
exists anywhere in this system.

**Round 2** — schema corrected by reading `painter.py`'s `_paint_canvas_*` methods and
`premium_pdf.html`'s `render_canvas_element` macro directly, field-for-field, plus an
explicit instruction: no `image`/icon elements without a real asset path, represent
icons/motifs with `shape` primitives only. Result: 15 elements, **zero unexpected
keys** against the real per-type field sets, 21.65s latency. The model represented the
mined signature's `icon_center` motif as two concentric circles (translucent halo +
solid center) instead of an icon glyph — a reasonable, renderable degradation, not a
failure. `design_reasoning` correctly named the reused motifs (`ribbon_band` as a
header/footer accent bar, the KPI-trio spatial rhythm at consistent y-offsets).

## Decision — Touchpoint A (`MineLayoutGrammarTool`)

Use `generate_json(..., specialization="general")` — this is a classification/naming
task over already-extracted geometry, not composition; the premium channel isn't
needed here and paying for it on every mined slide across every future brand would be
wasteful. Whatever provider `extraction_synthesis_model` resolves to (via
`system_configs`) is a fine target for this touchpoint.

## Validation — Touchpoint A (live, hit `gemini-flash-latest`)

Fed 2 hand-built geometry clusters (standing in for `template_analyzer.py`'s future
PDF-path output — the PDF extraction itself is Phase 0 implementation work, out of
scope for this call-structure validation) — one strong cluster (3 slides, near-identical
slot geometry) and one weak one (1 slide). Response: 2 correctly-named signatures,
correct `content_shape` classification (`metric_comparison` vs `cover`), and — notably,
this wasn't hardcoded into the prompt as a formula, only instructed qualitatively —
`confidence: 0.85` for the 3-slide cluster vs `confidence: 0.4` for the 1-slide one.
10.85s latency, valid JSON on first attempt, no `json_repair` fallback needed.

## Phase 3 — QA judge bias audit: CONFIRMED, not deferred

Two findings, one structural (from reading the code) and one behavioral (from a live
call):

**Structural**: `ScoreFidelityTool.run()` (`agents/qa_validator.py`) builds
`slides_context` from `title`, `layout_selected` (a slug string), `assigned_image`
metadata, `degraded_asset_quality`, and `planning_reasoning` (free text) —
**`canvas_elements` is never included**. The judge is composition-blind today, for
`v1` slides and any future `v2_artistic` slide alike. This means Phase 2's renderer
work doesn't change what the judge can evaluate at all — the geometry it would render
is invisible to QA regardless of which renderer draws it.

**Behavioral** (live, `gemini-flash-latest`, exact production prompt template from
`agents/qa_validator.py`, only `planning_reasoning`/`layout_selected` varied, brand
strategy and image signals held identical):

| Case | `layout_selected` | `planning_reasoning` (paraphrased) | Score | `needs_rework` |
|---|---|---|---|---|
| `safe_grid` | `data_grid` | "standard 3-column data grid, matches existing template" | **0.95** | false |
| `bold_asymmetric` | `custom_canvas` | "bold asymmetric canvas, bleeding ribbon band, uneven KPI heights, deliberate visual tension, reuses brand's donut-icon motif" | **0.68** | false |

The lower score's own `reasoning` field states the composition *"slightly clashes with
a disciplined, data-driven corporate financial tone, which prioritizes clean grid
alignment and clear readability"* — explicitly penalizing boldness as a brand-fit
violation, not any actual defect. This is the exact failure mode the design doc
flagged as a risk to check (`docs/designs/artistic-generation-v2.md`, Phase 3); it is
now a measured, reproducible 0.27-point penalty via the only channel that currently
reaches the judge.

**Recommendation to Architect** (escalating beyond what this ADR can decide alone):
1. Phase 3 must ship a versioned `prompt_score_fidelity_v2_artistic` **before** any
   `v2_artistic` job runs the standard retry loop — not conditionally, per the design
   doc's original "if bias is confirmed" framing. It is confirmed.
2. A reworded judge prompt alone doesn't fix the structural gap — `slides_context`
   needs an actual `canvas_elements` summary (element count/type mix; whether any
   element's `x + w` or `y + h` exceeds 100, a real geometry defect worth penalizing)
   for `v2_artistic` jobs, or the "improved" v2 judge is still validating brand-strategy
   *text*, never the composition it's meant to gate.

## Request shapes

```python
# Touchpoint B — ComposeCanvasTool
from providers.llm_provider import generate_premium_json
result = generate_premium_json(prompt)   # claude-sonnet-4-5, dedicated channel

# Touchpoint A — MineLayoutGrammarTool
from providers.llm_provider import generate_json
result = generate_json(prompt, specialization="general")
```

## Response shapes (field paths confirmed live)

```
# Touchpoint B
result["content_shape"]           str
result["canvas_elements"]         list[dict], each dict MUST use exactly:
  type == "text":              x, y, w, h, content, size, weight, color
  type == "shape"/"decorator": x, y, w|size, h, shape, color, opacity,
                                radius (rect only), border (optional), rotation (optional)
  type == "line":               x1, y1, x2, y2, stroke, strokeWidth
  type == "gradient_overlay":   x, y, w, h, gradient (CSS linear-gradient(...) string)
  type == "image":              x, y, w, h, path (a REAL BrandAsset path — never invent one)
result["design_reasoning"]        str

# Touchpoint A
result["signatures"]              list[dict]:
  name                str  (kebab-case)
  source_slide_indices list[int]
  content_shape        str, one of metric_comparison|narrative|quote|cover
  slots                list[dict]  (echoes input slot geometry)
  motifs               list[str]
  confidence           float 0.0-1.0
```

## Parameters

| Parameter | Value | Reason |
|---|---|---|
| Touchpoint B provider | `generate_premium_json()` (Claude Sonnet 4.5) | `specialization="design"` is dead code in `generate_json`; this is the only reliably-Anthropic path that exists today |
| Touchpoint A provider | `generate_json(..., specialization="general")` | classification, not composition — premium channel cost unjustified here |
| Touchpoint B prompt | must enumerate exact per-type field names | round 1 proves the model happily invents a plausible-but-wrong schema when only told the concept, not the contract |
| Touchpoint B icon handling | forbid `image`/icon elements without a real asset path; instruct shape-primitive fallback | no icon glyph library exists in this system; validated live that Claude produces a tasteful fallback (concentric circles) when told to |

## Restricciones conocidas

- `generate_premium_json()` latency: ~21-23s per slide in both rounds — real per-slide
  cost for Phase 1's rollout planning (Architect/PM concern, not resolved here).
- Local validation ran with `DATABASE_URL` unreachable (`db` hostname is Docker-internal),
  so `extraction_synthesis_model` fell through to its hardcoded default
  (`gemini-flash-latest`) rather than whatever `system_configs` holds in a real
  deployment — same caveat every other `generate_json` ADR in this repo carries.
- Pre-existing, unrelated to this feature but newly surfaced while reading both
  renderers side-by-side for the schema fix: `painter.py`'s canvas text supports
  center/left `align`; `premium_pdf.html`'s `render_canvas_element` macro has **no**
  alignment handling for `text` elements at all. Not exercised by either validation
  round above (neither test asked for centered text), but will surface the first time
  v2 output does — flagging for Phase 2, not fixing here.

## Notas

- The single most important implementation note in this ADR: **`ComposeCanvasTool`'s
  prompt must hardcode the exact renderer field vocabulary**, not a description of
  `canvas_elements` in general terms. Round 1's failure was silent — no exception, no
  malformed JSON, just confidently wrong field names that both renderers'
  `.get(...)`/`|default(...)` fallbacks would have swallowed into visually broken
  defaults (missing font size/weight, unresolvable image paths logged-and-skipped per
  slide with no surfaced error).
- Phase 3's finding changes the design doc's own sequencing risk: it was written as "if
  bias is confirmed" — treat it going forward as "bias is confirmed, judge fix is a
  Phase 1 prerequisite for anything beyond a manually-reviewed pilot batch," not a
  parallel Phase 3 workstream that can lag behind Phase 1 implementation.
