# ADR: Deck-level layout diversity (Analyst v4 / Art Director v4)

**Date validated**: 2026-09-21 (live `test-ai-request` run — see Validation below)
**Validated by**: AI Architect
**Status**: VALIDATED — approved for Synthesis Studio v2 Phase 2
**Used in**: `services/generation/analyst_service.py` (`get_slide_visual_strategy`), `services/generation/art_director_service.py` (`plan_presentation_design`)
**Spec**: `docs/specs/synthesis-studio-v2.md` (Phase 2 finding)

---

## Decision

Both existing per-slide LLM calls (Analyst, Art Director) gain a new placeholder fed
from the same real data: the `layout_slug` history of the deck built so far
(`get_recent_layout_history()`, shared helper, window = `system_configs.
layout_diversity_window`, default 6). No new touchpoint, no new call site, same
`generate_json`/`generate_premium_json` entry points as before — `specialization`
unchanged for both (`"general"` for Analyst, `"design"` for Art Director, same as
pre-existing).

**Why this shape**: Phase 2's re-measurement (regenerating the same 4 decks after
Findings 1-4 shipped) showed the vocabulary-collapse bug was genuinely fixed, but
real decks still settled into a 2-layout ping-pong (`pillars`/`data_grid` alternating
~8 times each in a 20-slide deck) — never 3 consecutive repeats, so it never tripped
the Art Director's existing "don't repeat the immediately previous layout" rule, and
the Analyst (which sets the baseline `grammar_type` before the Art Director's
optional override) had **zero** visibility into the deck at all. Confirmed via the
actual `layout_slug` sequence on 3 independently-generated decks (A/B/D) — identical
alternation pattern in all 3, ruling out one-off LLM randomness.

## Validation (live test, 2026-09-21)

Executed via the production entry points with real keys, real seeded prompt text
(`prompt_analyst_v4`, `prompt_art_director_v4`) — NOT mocked. Deliberately fed an
adversarial `recent_layouts`/`visual_history` input (`["pillars", "data_grid",
"pillars", "data_grid", "pillars", "data_grid"]`) to see whether the new instructions
actually change behavior, not just render without error:

- **Analyst** (`gemini-flash-latest`, Mistral's first hop 403'd as usual, chain
  degraded correctly): given the ping-pong history, returned
  `"grammar_type": "split"` — broke out of the pillars/data_grid loop.
- **Art Director** (`gemini-flash-latest`): returned
  `"suggested_layout_override": "custom_canvas"`, with `visual_reasoning` **explicitly
  naming the pattern**: *"The visual history shows an alternating ping-pong between
  'pillars' and 'data_grid'. To break this pattern and avoid repetitive structures,
  we select 'custom_canvas'."* — plus a well-formed `canvas_elements` array (2 big-
  number text pairs), confirming the response shape is unchanged from v3.
- Both calls succeeded on the first attempt, valid JSON, no `json_repair` fallback
  needed.

**Full-deck confirmation**: re-generated deck A (free/pptx, the deck Luis marked in
both elicitation rounds) end-to-end after seeding these prompts — see
`docs/specs/synthesis-studio-v2.md` for the resulting `layout_slug` sequence and
Luis's re-review.

## Request shape

```python
from services.generation.analyst_service import get_recent_layout_history

recent_layouts = get_recent_layout_history(db, job.id, slide.slide_number)  # window=6 default
recent_layouts_display = json.dumps(recent_layouts) if recent_layouts else \
    "[] (no previous slide has a layout assigned yet)"

# Analyst — specialization="general", unchanged
prompt = cfg_analyst_v4.value.format(
    slide_title=slide.title, bullets=str(slide.content_json.get("bullets", [])),
    rag_context=rag_context, recent_layouts=recent_layouts_display,
)
strategy = generate_json(prompt, specialization="general")  # or generate_premium_json if is_premium

# Art Director — specialization="design" via generate_premium_json when is_premium,
# else generate_json(..., specialization="general") — both pre-existing, unchanged.
# visual_history already existed; only its window widened (3 -> layout_diversity_window).
```

## Response shape (consumed field paths — unchanged from v3, confirmed live)

```
# Analyst v4 — same shape as v3
strategy["visual_intent"]        str
strategy["suggested_keywords"]   list[str]
strategy["grammar_type"]         str, one of hero|split|data_grid|pillars|custom_canvas
strategy["metric_value"]         str | null

# Art Director v4 — same shape as v3
decision["primary_asset_id"]           int | null
decision["accent_asset_id"]            int | null
decision["visual_reasoning"]           str
decision["suggested_layout_override"]  str | null, same 5-value vocabulary
decision["canvas_elements"]            list[dict] — text/image/typo_substitution/
                                        shape/decorator/line/gradient_overlay
                                        (see Finding 1b's builder,
                                        docs/specs/synthesis-studio-v2.md)
```

## Parameters

| Parameter | Value | Reason |
|---|---|---|
| `specialization` (Analyst) | `"general"` | unchanged from v3 — editorial/content-adjacent judgment |
| `specialization` (Art Director) | `"design"` | unchanged from v3 — pre-existing, note this doesn't currently route to Anthropic in `generate_json` (see `docs/ai/contracts/deck-design-brief-adr.md`, Finding 2 — orthogonal, not touched here) |
| `layout_diversity_window` | 6 (`system_configs`) | shared by both prompts so they reason over the identical deck slice; was hardcoded to 3 for the Art Director and nonexistent for the Analyst |

## Restricciones conocidas

- The diversity rule is advisory, not enforced in code — an LLM can still choose to
  repeat if it judges the content genuinely calls for it (by design: the prompt
  explicitly says "never force a mismatch just to add variety"). This ADR validates
  the mechanism works when tested adversarially; it does not guarantee every future
  deck is perfectly diverse — that's Phase 2's re-measurement to judge qualitatively,
  not something to assert from one live call.
- Same Mistral 403 (`tier_not_allowed`) already documented in
  `deck-design-brief-adr.md` — both calls in this validation fell through to
  `gemini-flash-latest`, consistent with every other `generate_json` call in this
  project today.

## Notas

- No new AI touchpoint, no new provider, no schema change — the live validation here
  is lighter-weight than a from-scratch ADR by design (same discipline as any prompt
  wording change on an already-validated call site), but still a real, non-mocked
  call per project convention, not just template-rendering confirmation.
