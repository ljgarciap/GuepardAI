# ADR: Deck Design Brief prompts (Architect v3 / Outline v3 / Narrator v2)

**Date validated**: 2026-09-18 (live `test-ai-request` run — see Validation below)
**Validated by**: AI Architect
**Status**: VALIDATED — gate satisfied for `docs/specs/coherencia-artistica-pipeline.md`, approved for Senior Reviewer sign-off
**Used in**: `services/generation/content_service.py` (`synthesize_presentation_outline`, Steps 2-3), `agents/narrator.py` (`NarratorTool`, Step 4.5)
**Spec**: `docs/specs/coherencia-artistica-pipeline.md`

---

## Decision

Three prompts gain a Deck Design Brief signal (`deck_brief_service.build_deck_brief()`) on
top of their existing `_v2`/`v1` behavior — no new touchpoints, no new call sites, same
`generate_json(prompt, specialization=...)` entry point as before:

| Prompt key | Call site | `specialization` | New placeholders |
|---|---|---|---|
| `prompt_architect_v3` | `content_service.py:206` | `"general"` | `{deck_brief}` |
| `prompt_content_outline_v3` | `content_service.py:221-230` | `"general"` | `{preferred_grammar_types}`, `{opening_closing_hint}` |
| `prompt_narrator_v2` | `narrator.py:84` | `"design"` (pre-existing, unchanged by this spec) | `{visual_density}`, `{preferred_grammar_types}` |

**Why default/general routing for Architect and Outline**: confirmed with the Architect's
closure on the spec — this is editorial/content framing, not visual/layout judgment.
**Why `specialization="design"` for the Narrator is unchanged**: pre-existing since v1,
not part of this spec's scope (see finding below on what that parameter currently does).

**Degradation contract** (unchanged from spec, confirmed live): when a brand has no
`BrandArtisticEssence`, `build_deck_brief()` returns `{}`, and `deck_brief`/
`preferred_grammar_types`/`opening_closing_hint`/`visual_density` are formatted as empty
string / "No strong preference — use your own judgment." / `"balanced"` respectively —
`str.format()` never raises on the unused kwargs when a `_v1`/`_v2` prompt is loaded
instead. Confirmed by `test_seed_prompts_deck_brief.py` (mocked) and live in this run
(non-empty brief rendered correctly into all three prompts, see Request shape below).

## Validation (live test, 2026-09-18)

Executed via the production entry point (`generate_json`) with real keys from `.env` and
the real seeded `system_configs` rows (`prompt_architect_v3`, `prompt_content_outline_v3`,
`prompt_narrator_v2`, `extraction_synthesis_model`) against the local dev Postgres — NOT a
mock, NOT a mocked `generate_json`. Script: one-off, not committed (`generate_json` calls
only, no DB writes).

- **Model chain configured**: `extraction_synthesis_model` = `mistral/mistral-large-latest,gemini-flash-latest,anthropic/claude-sonnet-4.6`
- **Provider actually selected (all 3 calls)**: `mistral/mistral-large-latest` → **403** (`tier_not_allowed`, code `1910`, "This model is not available in your subscription tier") → chain correctly fell back to **`gemini-flash-latest`** (native `google-genai` SDK, `GOOGLE_API_KEY`), which served all 3 requests successfully.
- **Latency**: Architect 11.79 s, Outline 8.60 s, Narrator 11.06 s (~31.5 s sequential total — in line with the outline ADR's existing per-job budget for Steps 2-4.5).
- **Result**: valid JSON on the first attempt for all 3 (no `json_repair` fallback needed), all consumed field paths present and typed, non-empty `deck_brief` content visibly shaped the output (see Request/Response below).

### Finding 1 (blocking for cost/availability, not for this spec's merge) — Mistral tier rejection

`mistral/mistral-large-latest`, the first hop of `extraction_synthesis_model` for every
`generate_json` call in the project (not just these 3 prompts), returns HTTP 403
`tier_not_allowed` with the current `MISTRAL_API_KEY`. The fallback chain absorbs this
correctly today (→ `gemini-flash-latest`), so no user-facing failure — but it means 100%
of `generate_json` traffic is silently running one hop down the chain, with no alerting.
**Not caused by this spec, pre-existing account/billing state** — flagged here because
`test-ai-request` exists precisely to surface this instead of assuming the chain works
from documentation/memory. Recommend a separate ticket to either restore the Mistral tier
or drop it from the chain's first position; out of scope to fix inside this spec's PR.

### Finding 2 (informational, out of scope per Arquitecto's decision #3) — `specialization="design"` does not route to Anthropic today

`resolve_provider()` in `providers/llm_provider.py` (lines 100-128) implements the
"`specialization="design"` → Anthropic Claude" rule described in `GuepardAI/CLAUDE.md`
("LLM Provider Routing"), but **`generate_json`/`_generate_json_raw` never call
`resolve_provider()`** — model selection in that path is purely by model-name string
matching (`"gemini"`, `"mistral" + "/"`, else OpenRouter) against
`extraction_synthesis_model`, regardless of `specialization`. Confirmed live: the
Narrator call (`specialization="design"`) hit the exact same `mistral → gemini` fallback
as the two `specialization="general"` calls — no Anthropic call was ever attempted.
`resolve_provider()` is currently dead code (no other call site in the codebase).

This predates this spec (`prompt_narrator_v1` already passed `specialization="design"`)
and the Arquitecto's decision #3 explicitly keeps `prompt_architect_v3`/
`prompt_content_outline_v3` on `"general"` — so nothing in this spec regresses or needs
this fixed to merge. Flagging per AI Architect jurisdiction ("flag deprecated or changed
provider behavior before it hits implementation") so it doesn't get assumed-fixed later:
CLAUDE.md's routing table is aspirational for this call path today, not actual behavior.
Recommend a follow-up decision (Architect-level, not blocking) on whether to wire
`resolve_provider()` into `_generate_json_raw` or remove it as dead code.

## Request shape

```python
from providers.llm_provider import generate_json
from services.generation.deck_brief_service import format_grammar_type_list, summarize_for_architect_prompt

# deck_brief as build_deck_brief() would return for a brand WITH BrandArtisticEssence
deck_brief = {
    "tone_note": "Confident, data-driven, understated luxury tone; short declarative sentences, no hype adjectives.",
    "visual_density": "balanced",
    "preferred_grammar_types": ["cover_hero", "executive_quote", "data_grid_cards"],
    "opening_closing_hint": "Opening: full-bleed hero with a single bold claim; Closing: quote-style CTA reinforcing the claim.",
}

# 1) Architect v3
architect_prompt = cfg_architect.value.format(
    topic=topic, brand_name=brand_name, tone_guideline=tone_guideline,
    deck_brief=summarize_for_architect_prompt(deck_brief),
)
architect_resp = generate_json(architect_prompt, specialization="general")

# 2) Outline v3
outline_prompt = cfg_outline.value.format(
    polished_prompt=architect_resp["polished_instruction"], rag_context=initial_rag,
    target_lang=region,
    preferred_grammar_types=format_grammar_type_list(deck_brief["preferred_grammar_types"]),
    opening_closing_hint=deck_brief["opening_closing_hint"],
)
outline_resp = generate_json(outline_prompt, specialization="general")

# 3) Narrator v2
narrator_prompt = cfg_narrator.value.format(
    slides_json=json.dumps(compact_slides), brand_name=brand_name, target_lang=region,
    strategic_context=strategic_context, slide_count=len(compact_slides),
    visual_density=deck_brief["visual_density"],
    preferred_grammar_types=format_grammar_type_list(deck_brief["preferred_grammar_types"]),
)
narrator_resp = generate_json(narrator_prompt, specialization="design")
```

## Response shape (consumed field paths — all confirmed present and typed in the live run)

```
# Architect v3
architect_resp["polished_instruction"]   str — 17-slide narrative brief, no [bracket] placeholders,
                                          visibly informed by deck_brief's tone/density/opening-closing hint
architect_resp["strategic_rationale"]    str

# Outline v3
outline_resp["slides"]                   list, 15-20 entries (observed: 17)
outline_resp["slides"][i]["title"]       str, <=55 chars
outline_resp["slides"][i]["section_label"] str
outline_resp["slides"][i]["layout_type"] str, from the Allowed list only — observed
                                          {composition_hero, composition_split,
                                          composition_pillars, data_grid_cards}; the
                                          BRAND VISUAL RHYTHM values (cover_hero,
                                          executive_quote — a DIFFERENT vocabulary) were
                                          NOT leaked into layout_type, confirming the
                                          prompt's "soft signal, not literal values"
                                          framing held under a real model

# Narrator v2
narrator_resp["corrections"]             list (observed: 1 of 3 slides, 33% <= 40% cap)
narrator_resp["corrections"][i]["slide_index"]  int
narrator_resp["corrections"][i]["field"]        str, observed "subtitle" (within
                                                 {subtitle, bullets, objective})
narrator_resp["corrections"][i]["new_value"]    str
narrator_resp["corrections"][i]["reason"]       str
narrator_resp["cohesion_score"]          float 0.0-1.0 (observed: 0.75)
narrator_resp["gaps_found"]              list[str] (observed: 2 entries, one referencing
                                          the empty-subtitle cover, one referencing the
                                          closing slide — matches the prompt's own
                                          "WHAT TO LOOK FOR" checklist)
```

Parsing is unchanged from pre-existing behavior: `clean_json_string()` strips markdown
fences, `json.loads()` first, `json_repair` as fallback (not needed in this run — all 3
responses parsed on the first attempt).

## Parameters

| Parameter | Value | Reason |
|---|---|---|
| `specialization` (Architect, Outline) | `"general"` | editorial/content framing, not visual judgment — Arquitecto decision #3 |
| `specialization` (Narrator) | `"design"` | pre-existing since v1, unrelated to this spec; currently a no-op for provider routing (Finding 2) |
| `extraction_synthesis_model` chain | `mistral/mistral-large-latest,gemini-flash-latest,anthropic/claude-sonnet-4.6` | unchanged `system_configs` value; first hop currently 403s (Finding 1), chain degrades correctly |
| `deck_brief_field_max_chars` | 400 (from `system_configs`) | truncates `tone_note`/`opening_closing_hint` before interpolation, confirmed non-hardcoded |

## Restricciones conocidas

- Mistral tier rejection (Finding 1) adds one wasted round-trip + the 403 latency to
  *every* `generate_json` call project-wide, not just these 3 — until resolved, expect
  the effective model for this feature to be `gemini-flash-latest`, not Mistral.
- `specialization="design"` provides no routing guarantee today (Finding 2) — do not
  assume the Narrator call is running on Claude; it is not.
- Latency adds ~30s sequential across Architect + Outline + Narrator before/around the
  per-slide `ThreadPoolExecutor` step — acceptable, no change from pre-spec baseline
  (the calls already existed; only their prompt bodies grew).

## Notas

- This ADR does not re-validate the Outline's per-slide content call (`SlideContentTool`)
  or the RAG embedding call (`search_rag`/`get_embedding`) — both untouched by this spec
  and already covered by their own prior ADRs / production behavior.
- Confirms the spec's Acceptance criteria items for "prompt renderizado contiene los
  valores del brief" and "degrada limpio sin esencia" under a real model, not just the
  mocked unit tests in `test_content_service_deck_brief.py` / `test_seed_prompts_deck_brief.py`.
