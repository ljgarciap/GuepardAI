# Design Proposal: Template Merge v2 — Structural Fidelity & Content Quality

**Date**: 2026-07-07
**Authors**: Architect (lead) + AI Architect + Senior Backend (joint analysis)
**Status**: APPROVED by Luis (2026-07-07). Phase 1 in implementation.
**Spec**: `docs/specs/template-merge-v2-quality.md`
**Baseline**: `docs/designs/template-merge.md` (as-built v1), `docs/specs/template-merge.md`
**Scope guard**: This proposal only touches the Template Merge path
(`backend/services/templates/`). The classic generation pipeline
(Redactor → Architect → Render) is explicitly out of scope.

---

## 1. Assessment of the current approach (v1)

### What v1 gets right (keep, do not rewrite)

1. **Structure preservation by construction** — the renderer copies the
   template file and only swaps text runs in place (`template_renderer.py`).
   Images, backgrounds, positions, and theme formatting survive because they
   are never touched. This is the strongest possible fidelity guarantee and
   the correct architectural foundation. Any alternative (re-rendering from a
   parsed model) would be strictly worse.
2. **Deterministic, LLM-free structural analysis** — cheap, fast, testable
   (88% coverage today). Correct call.
3. **Resilience model** — per-slide degradation, top-level error persistence
   with a second DB session, thin Celery task, config via `system_configs`
   (`tm_*` keys). All consistent with project conventions.
4. **Clean layering** — analyzer / content / renderer / orchestrator, each
   single-purpose. v2 extends this layering; it does not replace it.

### Where v1 falls short of "aesthetically striking and professional"

Ordered by impact. Findings A–C are correctness/professionalism defects;
D–G are quality gaps.

**A. Text inside groups and tables is invisible (stale template text ships in the output).**
`analyze_template` iterates `slide.shapes` flat and gates on
`shape.has_text_frame` (`template_analyzer.py:90`). In python-pptx, a
`GroupShape` and a table-bearing `GraphicFrame` both report
`has_text_frame == False`, and the loop never recurses into them. The
renderer has the same blind spot. Real agency decks are full of grouped
text blocks and data tables — every one of them keeps the **original
template's text** in the merged output. This alone can make a merged deck
look broken. (Verified: zero occurrences of `GroupShape`/`shape_type`/table
handling in `services/templates/`.)

**B. "No relevant data" keeps the template's dummy text.**
The prompt instructs the LLM to return `""` when the knowledge base has
nothing for a slot (rule 9, `template_content.py:216`), and the renderer
treats empty strings as "keep original" (`template_renderer.py:92`). Net
effect: slides the RAG couldn't fill ship with the template's placeholder
prose mixed in with new content — the worst possible failure mode for a
client-facing deck, and it is silent (no report, no flag).

**C. Bullet lists collapse into a single paragraph.**
`_set_paragraph_text` writes all generated lines into the *first* paragraph
separated by `<a:br>` soft breaks and blanks the rest. A template body
designed as 4 bulleted paragraphs renders as one bullet glyph followed by
soft-wrapped lines, plus empty bullet paragraphs below. Visually degraded
versus the template's intent. Per-paragraph `pPr` (bullet char, indent,
spacing) is being discarded.

**D. RAG retrieval is queried with the OLD template's text.**
`rag_query = profile.hint` (`template_content.py:79`) — the hint is the
template's existing titles. When the template's subject differs from the
knowledge document (the common case — e.g. the test template "Harry Potter
y DC" merged with corporate knowledge), the vector search retrieves chunks
similar to the *old* deck, not chunks relevant to the *new* content. The
grounding quality of the whole feature hinges on this query and it is
currently pointed at the wrong thing.

**E. No narrative coherence across slides.**
One independent LLM call per slide, no shared outline, no memory of what
previous slides said. Result: repeated points, no story arc, inconsistent
terminology and tone across the deck. A professional deck is a narrative,
not N disconnected slides.

**F. Char budgets ignore typography; overflow handling is truncation.**
`chars_per_sq_inch = 30` flat (`template_config.py:39`) regardless of font
size — a 40pt title box and a 12pt body box of equal area get the same
budget (~10× real difference). Overflow is handled by hard truncation with
`…`, which reads as an error to any reader. Additionally, templates using
PowerPoint autofit (`normAutofit` with a stored `fontScale`) keep the old
scale after replacement, so longer text can visibly overflow until manually
edited.

**G. Output language is unpinned.**
The prompt never states a target language; the old template's hints can
drag the output into the template's language instead of the knowledge
document's / user's.

---

## 2. Target architecture (v2 — evolution, not rewrite)

Same four modules, two new stages, two hardened stages:

```
 analyze          (HARDEN: recurse groups, address table cells, capture
    │              per-paragraph formatting + font sizes → typographic budgets)
    ▼
 plan             (NEW: ONE LLM call for the whole deck — narrative outline
    │              mapping the knowledge doc onto the template's slide
    │              sequence: per-slide topic, key points, RAG query,
    │              target language, tone)
    ▼
 generate         (HARDEN: per-slide calls now receive the outline + a
    │              1-line summary of what previous slides covered; RAG query
    │              comes from the plan, not the old template text)
    ▼
 fit-check        (NEW: deterministic — estimate rendered text extent from
    │              font size + box dims; one "shorten" retry per failing
    │              slot; truncation only as last resort)
    ▼
 render           (HARDEN: paragraph-per-line for originally-bulleted
    │              frames reusing each paragraph's pPr/rPr; groups + table
    │              cells; explicit empty-slot policy)
    ▼
 merge report     (NEW: per-slot outcome — rewritten / adapted / preserved /
                   unfilled — persisted on the job, surfaced in the UI)
```

Optional, config-gated (default OFF): a visual QA pass that renders the
merged deck to images (LibreOffice, already in the Docker image) and asks a
Vision LLM to flag overflow/contrast issues. Spends tokens → behind
`tm_visual_qa_enabled` in `system_configs`, mirroring the
`auto_data_alignment_enabled` kill-switch precedent.

### Key design decisions

**D1 — Slot addressing becomes a string key.**
Today the content map is `Dict[int, str]` keyed by `shape_id`. Groups and
table cells need composite addresses. New scheme (internal only, no API
change): `"42"` plain shape, `"42/17"` shape 17 inside group 42,
`"42:r2c3"` table cell. Analyzer and renderer share one
`resolve_slot(slide, key)` helper so addressing can never diverge between
the two.

**D2 — Empty-slot policy is explicit and reported.**
For `action="rewrite"` slots where the LLM returns `""`: default becomes
**blank the text** (professional: an empty box beats lorem ipsum) and record
`unfilled` in the merge report. For `action="adapt"` slots, keep the
original (the hint *is* meaningful there). Both behaviors overridable via
`tm_empty_rewrite_policy` (`blank` | `keep`). The merge report makes the
outcome visible instead of silent.

**D3 — The plan pass is one call, not per-slide; per-slide calls stay.**
A whole-deck single call for final content would blow context/JSON limits on
large decks and lose the per-slide failure isolation v1 already has. The
outline call is small (slide skeletons in, ~1 short JSON out) and buys
narrative coherence + correct RAG queries for every downstream call.
Failure of the plan call degrades gracefully to v1 behavior (hint-based
queries, no outline context) — never aborts the job.

**D4 — Typographic budget replaces area budget.**
The analyzer already touches each run's `rPr`; capture the dominant font
size per slot and compute `char_limit` from `(box_width / avg_char_width(pt)) ×
(box_height / line_height(pt))` with a safety factor. Keep
`chars_per_sq_inch` as fallback when no size is resolvable. Same
`system_configs` discipline (`tm_char_width_factor`, `tm_line_height_factor`,
`tm_fill_safety_factor`).

**D5 — Fit-check is deterministic first, LLM second, truncation last.**
Overflowing slots get one regeneration request ("shorten to N chars, keep
the key point") batched per slide; only if still overflowing do we truncate
at a sentence boundary (not word boundary — cleaner). Bounded cost: at most
one extra LLM call per slide, only for slides that failed.

### AI Architect notes (touchpoint changes)

- **New touchpoint**: the deck-outline call. Content-synthesis in nature →
  default routing (no `specialization=`), same rationale as the existing ADR.
  Requires a **new ADR** (`docs/ai/contracts/default-llm-template-merge-outline-adr.md`)
  validated with a live `test-ai-request` run before merge (it IS a new
  prompt shape — the retroactive-validation exception does not apply).
- **Changed touchpoint**: the per-slide call gains outline context,
  prev-slide summaries, language pinning, and a shorten-retry variant. Per
  `ai-architect.md` jurisdiction ("any call structure that differs from the
  last validated ADR"), this supersedes
  `default-llm-template-merge-content-adr.md` → write v2 of that ADR.
- **Optional touchpoint** (Phase 4 only): Vision QA call — needs its own ADR
  if/when Phase 4 is approved; routed via `generate_vision_json`.
- RAG: no embedding/provider change. Improvement is query construction only
  (plan-derived queries + cross-slide chunk de-duplication so the same chunk
  doesn't dominate every slide). No new vector dimensions, no new indexes.

### Senior Backend notes (implementation constraints)

- All new tunables via `TemplateMergeConfig` + `tm_*` keys in `seed.py`
  (seeder skips existing keys — all new keys, no edits to existing ones).
- `merge_report` = JSON column on `TemplateMergeJob`, added via the standard
  idempotent `ALTER ... IF NOT EXISTS` startup layer in `database.py`; no
  data alignment needed (new column, no backfill).
- Group recursion must cap depth (malformed decks can nest deep) and must
  preserve v1's shape-level filtering semantics (area thresholds computed
  against the *group child's* effective size).
- Renderer paragraph handling: when original frame has ≥2 non-empty
  paragraphs, map generated lines 1:1 onto existing paragraphs (reusing each
  paragraph's `pPr` + first-run `rPr`), reuse the last paragraph's format
  for extra lines, blank the leftovers. Single-paragraph frames keep v1's
  `<a:br>` behavior.
- Autofit: if the frame carries `normAutofit` with `fontScale`, strip the
  stale `fontScale`/`lnSpcReduction` after replacement so PowerPoint
  recomputes on open (config-gated `tm_reset_autofit`, default on).
- Hygiene (fold into Phase 1): move the 5 `/api/template-merge/*` endpoints
  from `main.py` to `backend/routers/template_merge.py` per the routers
  convention, keeping auth + tenant scoping via `auth/dependencies.py`
  helpers. Behavior-neutral, aligns with the standing rule.
- Testing per phase follows the standing sequence: manual local first, then
  unit, then integration, then coverage confirmation. Existing 61 tests must
  keep passing; new heuristics get the same unit-test treatment as v1's.

---

## 3. Action plan (phased, each phase independently shippable)

| Phase | Content | Fixes | AI changes | Est. |
|---|---|---|---|---|
| **0. Governance** | Analyst spec for v2 (this doc is the design input); AI Architect ADRs (outline ADR + content ADR v2) | — | ADRs only | 0.5 d |
| **1. Structural coverage** | Group recursion, table cells, string slot addressing (D1), bullet-aware paragraph rendering, empty-slot policy (D2), merge report column + status API + UI surface, endpoint migration to `routers/` | A, B, C | none | 2–3 d |
| **2. Narrative & grounding** | Plan pass (outline call), outline + prev-summaries in per-slide prompts, plan-derived RAG queries, chunk de-dup, language pinning | D, E, G | new outline touchpoint; content ADR v2 | 2 d |
| **3. Typographic fidelity** | Font-size-aware char budgets (D4), deterministic fit-check + shorten retry (D5), sentence-boundary truncation, autofit reset | F | shorten-retry variant (covered by content ADR v2) | 1.5–2 d |
| **4. Visual QA (optional)** | Render-to-image + Vision LLM overflow/contrast check, gated by `tm_visual_qa_enabled` (default off) | — | new Vision touchpoint + ADR | 2 d |

Recommended order is as listed: Phase 1 is the highest professionalism gain
at zero token cost and zero AI risk; Phases 2–3 deliver the "striking and
professional" content quality; Phase 4 is a nice-to-have gate to decide
after seeing 1–3 on real client templates.

Per-phase flow respects the standing process: PM task breakdown → Backend
Dev → Senior Reviewer → QA → Luis. Frontend involvement is small and
limited to Phase 1 (merge report display) unless the UI wants to expose
plan/outline preview later (out of scope for now).

## 4. Explicitly out of scope (v3 candidates, need their own spec)

- Adding/removing/reordering slides to fit the knowledge content's natural
  length (changes template structure — contradicts the core guarantee;
  would need a per-job opt-in and its own design).
- Per-slot manual overrides in the UI before generation.
- Image replacement/substitution inside the template.
- Any change to the classic generation pipeline.

## 5. Risks

| Risk | Mitigation |
|---|---|
| Group/table recursion changes slot counts on decks that "worked" in v1 | Merge report makes every slot outcome visible; integration tests pin v1 fixture behavior; thresholds stay config-tunable |
| Outline call adds 1 LLM call/job + prompt complexity | Single small call; graceful degradation to v1 behavior on failure (D3) |
| Fit-check retry doubles worst-case per-slide calls | Retry only on failing slides, once, bounded by `tm_fitcheck_max_retries=1` |
| Autofit reset alters decks that relied on stored fontScale | Config-gated `tm_reset_autofit`; validated on Luis's real client templates before default-on ships |
| New ADR-less AI touchpoints slipping in (v1's original sin) | Phase 0 is a hard gate: no Phase 2/4 code before the corresponding ADR exists |
