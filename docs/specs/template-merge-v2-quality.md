# Spec: Template Merge v2 — Structural Fidelity & Content Quality

**Date**: 2026-07-07
**Requested by**: Luis (approved the team proposal, same date)
**Status**: Approved — Phase 1 in implementation
**Design**: `docs/designs/template-merge-v2-quality.md` (approved 2026-07-07)
**Baseline**: `docs/specs/template-merge.md` (v1, as-built)

## Problem

v1 preserves template structure for simple decks but ships unprofessional
output on real agency templates: text inside grouped shapes and tables is
never replaced (stale template text survives), bullet lists collapse into a
single paragraph, slides the RAG couldn't fill silently keep the template's
dummy prose, content has no narrative coherence across slides, and char
budgets ignore typography. See design doc §1 for the full findings (A–G).

## Solution summary

Evolve the existing 4-module pipeline (keep copy-and-replace-in-place as the
fidelity guarantee) with two new stages (narrative plan, fit-check) and two
hardened stages (analyzer, renderer), plus a per-slot merge report. Delivered
in 4 phases; each independently shippable.

## Scope of this spec

Phases 1–3 as defined in the design doc. Phase 4 (visual QA) needs a go/no-go
from Luis after 1–3 land. The classic generation pipeline is untouched.

## Acceptance criteria

### Phase 1 — Structural coverage (no AI changes)

**Slot addressing**
- [ ] Slots are addressed by string keys: `"42"` (top-level shape),
      `"42/17"` (shape 17 inside group 42, recursive), `"42:r2c3"` (table
      cell row 2 col 3, 0-indexed). Analyzer and renderer share one
      traversal helper — they can never diverge.
- [ ] Group recursion is capped at `tm_group_max_depth` (default 3).

**Groups & tables**
- [ ] Text frames inside `GroupShape`s (any depth up to the cap) are
      analyzed, classified, and replaced exactly like top-level shapes.
- [ ] Table cell text is analyzed per cell (char limit derived from column
      width × row height) and replaced in place; table structure, merges,
      and cell formatting are never altered.
- [ ] Charts, SmartArt and other graphic frames without an accessible text
      frame are counted as preserved shapes (no crash, no attempt).

**Bullet-aware rendering**
- [ ] When the original text frame has ≥2 non-empty paragraphs, generated
      lines map 1:1 onto the original paragraphs, each reusing that
      paragraph's own `pPr` (bullet char/numbering, indent, spacing) and
      first-run `rPr`. Extra lines reuse the last original paragraph's
      formatting; leftover paragraphs are blanked.
- [ ] Single-paragraph frames keep v1 behavior (soft `<a:br>` breaks).

**Empty-slot policy**
- [ ] `action="rewrite"` slot + empty LLM value → text is blanked (default)
      and the slot is reported as `unfilled`. Behavior switchable via
      `tm_empty_rewrite_policy` (`blank` | `keep`).
- [ ] `action="adapt"` slot + empty LLM value → original text kept, reported
      as `kept_original`.

**Merge report**
- [ ] `TemplateMergeJob.merge_report` (JSON, nullable) stores, per slot:
      slide index, slot key, role, action, outcome
      (`rewritten` | `adapted` | `preserved` | `unfilled` | `kept_original`
      | `failed`), plus per-slide totals of untouched shapes.
- [ ] `GET /api/template-merge/jobs/{id}` returns `merge_report` (and a
      compact `merge_summary` with counts) when available.
- [ ] The template-merge UI shows the summary (at minimum: unfilled count
      with a warning when > 0) after completion.

**Hygiene**
- [ ] The 8 `/api/template-merge/*` endpoints move from `main.py` to
      `backend/routers/template_merge.py` (APIRouter), preserving existing
      auth + tenant scoping exactly. No URL, verb, or payload changes.

**Testing (Phase 1)**
- [ ] Manual local validation first (synthetic template with groups, a
      table, and bulleted bodies), then unit, then integration, then
      coverage — per standing testing sequence.
- [ ] Existing v1 tests keep passing (updated for string slot keys).
- [ ] New unit tests: group traversal (incl. depth cap), table cell slots,
      bullet paragraph mapping, empty-slot policy, merge report assembly.
- [ ] Integration: full pipeline over a synthetic PPTX containing a group,
      a table and a bulleted body; merged output verified shape-by-shape.

### Phase 2 — Narrative & grounding (new/changed AI touchpoints) — DONE 2026-07-07

- [x] One deck-level plan call (default routing) produces per-slide topic,
      key points, RAG query and target language; failure degrades to v1
      behavior without aborting the job (`template_plan.py`, gated by
      `tm_outline_enabled`).
- [x] Per-slide generation receives the outline + 1-line summaries of
      previous slides; RAG queries come from the plan, not template hints.
- [x] RAG chunks already used verbatim by a previous slide are de-prioritized
      (`_deprioritize_used_chunks`).
- [x] Output language is pinned (from plan; fallback: language of the user
      prompt).
- [x] ADRs exist BEFORE code merges: new outline ADR (validated with a live
      `test-ai-request` run, 2026-07-07) + content ADR v2 superseding
      `default-llm-template-merge-content-adr.md`.

### Phase 3 — Typographic fidelity

- [ ] Char budgets derive from dominant font size + box dimensions
      (`tm_char_width_factor`, `tm_line_height_factor`,
      `tm_fill_safety_factor`); area-based estimate remains as fallback.
- [ ] Deterministic fit-check after generation; overflowing slots get at
      most one batched shorten-retry (`tm_fitcheck_max_retries`, default 1);
      final fallback truncates at a sentence boundary.
- [ ] Stale autofit `fontScale`/`lnSpcReduction` is stripped after
      replacement (`tm_reset_autofit`, default on).

## Configuration (all new keys, seeded in `utils/seed.py`)

Phase 1: `tm_group_max_depth` (3), `tm_empty_rewrite_policy` (`blank`).
Phase 2: `tm_outline_max_chars`, plus prompt keys if templated.
Phase 3: `tm_char_width_factor`, `tm_line_height_factor`,
`tm_fill_safety_factor`, `tm_fitcheck_max_retries`, `tm_reset_autofit`.
Phase 4 (if approved): `tm_visual_qa_enabled` (off).

## Edge cases

- Group nested beyond depth cap → children beyond cap counted as preserved,
  logged, reported; never a crash.
- Table with merged cells → python-pptx exposes the merge origin cell only;
  spanned cells are skipped (reported `preserved`).
- Slot key present in LLM response but not resolvable at render time (deck
  mutated between analyze and render is impossible — same copy — so this
  indicates a traversal bug) → warning + `failed` outcome, job continues.
- Old jobs (pre-v2) have `merge_report = NULL` → API returns `null`, UI
  hides the section.

## Out of scope

Same as design doc §4: slide add/remove/reorder, per-slot manual overrides,
image replacement, any change to the classic pipeline.

## References

- Design: `docs/designs/template-merge-v2-quality.md`
- v1 spec: `docs/specs/template-merge.md`
- v1 ADR: `docs/ai/contracts/default-llm-template-merge-content-adr.md`
- Code: `backend/services/templates/`, `backend/routers/template_merge.py`
  (new), `frontend/src/app/pages/template-merge/`
