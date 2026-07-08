# ADR: Default-routed LLM call for Template Merge deck OUTLINE planning

**Date validated**: 2026-07-07 (live `test-ai-request` run — see Validation below)
**Validated by**: AI Architect
**Status**: VALIDATED — new touchpoint, approved for Template Merge v2 Phase 2
**Used in**: `services/templates/template_plan.py` — `plan_deck()`
**Spec**: `docs/specs/template-merge-v2-quality.md` (Phase 2)
**Design**: `docs/designs/template-merge-v2-quality.md` (§2, "plan" stage, decision D3)

---

## Decision

One LLM call per merge job (BEFORE the per-slide content calls) produces a
deck-level narrative plan: target language, tone, and per-slide topic /
key points / RAG query. The call goes through
`providers.llm_provider.generate_json(prompt)` with **no `specialization`**
(default routing: `ACTIVE_LLM` → Mistral → Gemini → OpenRouter chain from
`system_configs.extraction_synthesis_model`).

**Why default routing**: this is editorial/content planning, not
visual/layout judgment — same rationale as the per-slide content ADR.
**Why one small call and not per-slide planning**: the outline is what gives
slides narrative coherence; per-slide calls stay for content (JSON size and
failure isolation — design D3).

**Degradation contract**: any failure (LLM error, malformed JSON, missing
fields) returns `None` and the pipeline falls back to v1 behavior
(hint-based RAG queries, no outline context). The plan call must NEVER
abort a job. Gated by `system_configs.tm_outline_enabled` (default on) —
it spends tokens, so it gets a kill switch per project convention.

## Validation (live test, 2026-07-07)

Executed via the production entry point (`generate_json`, default routing)
with real keys — NOT a mock:

- **Provider selected**: `mistral/mistral-large-latest` (first hop of the chain)
- **Latency**: ~7.5 s for a 3-slide skeleton
- **Result**: valid flat JSON, all consumed field paths present and typed;
  Spanish knowledge sample correctly produced `"language": "es"`, slide-specific
  `rag_query` strings in the document's language, a visible narrative arc,
  and no repeated key points across slides.

Two defects found and fixed during this validation (the reason live tests exist):
1. `log_audit()` in `llm_provider.py` opened its file without
   `encoding="utf-8"` — on Windows any non-cp1252 char in a prompt (e.g. "→")
   crashed the whole provider call. Fixed (explicit utf-8 + errors="replace").
2. The model chains in `system_configs` ended in the stale slug
   `claude-3-5-sonnet-20241022`, which falls into the OpenRouter branch and
   returns 400 — the emergency fallback was dead in every deployed DB.
   Fixed via data alignment `stale_fallback_model_fix_v1`
   (→ `anthropic/claude-sonnet-4.6`, verified against OpenRouter's live
   model catalog).

## Request shape

```python
from providers.llm_provider import generate_json

prompt = """You are the editorial planner for a corporate presentation. An existing PPTX template will be refilled with new content from a knowledge document. Plan the narrative BEFORE any slide is written.

USER INTENT: {user_prompt}

KNOWLEDGE DOCUMENT SAMPLE (representative excerpts):
{outline_rag_context}                      # search_rag(user_prompt), k=tm_outline_rag_k, capped tm_outline_context_max_chars

TEMPLATE STRUCTURE ({n} slides — the plan MUST keep exactly this slide count and order):
  Slide {i}: slots=[{role}(limit {n}), ...] existing_hints="{hints}"

TASK: Map the knowledge onto this exact slide sequence as ONE coherent narrative (opening, development, close). No two slides may repeat the same key point.

Return ONLY a valid JSON object, no markdown fences:
{
  "language": "<ISO 639-1 code ...>",
  "tone": "<3-6 words>",
  "slides": [
    {"slide": 1, "topic": "<one line>", "key_points": ["..."], "rag_query": "<vector-search query in the knowledge document's language>"}
  ]
}
Rules:
1. Exactly one entry per slide, same order as the template.
2. key_points: 2-4 items, each a concrete fact to communicate, never invented.
3. rag_query must be specific to that slide's topic.
"""

raw = generate_json(prompt)   # no specialization= → default routing
```

## Response shape (consumed field paths)

```
raw["language"]                 str, ISO 639-1 (observed: "es")
raw["tone"]                     str
raw["slides"]                   list, one entry per template slide
raw["slides"][i]["slide"]       int, 1-based, template order
raw["slides"][i]["topic"]       str
raw["slides"][i]["key_points"]  list[str], 2-4 items
raw["slides"][i]["rag_query"]   str
```

Parsing is tolerant per-entry: an entry with a missing/invalid field is
dropped (that slide degrades to v1 behavior); a missing/invalid `slides`
list, or a non-dict response, degrades the whole plan to `None`.

## Parameters

| Parameter | Value | Reason |
|---|---|---|
| `specialization` | not set | editorial planning, not design judgment |
| Calls per job | exactly 1 (0 if `tm_outline_enabled` is off or deck has no active slots) | cost control |
| `tm_outline_rag_k` | `system_configs` (default 8) | chunks for the whole-doc sample |
| `tm_outline_context_max_chars` | `system_configs` (default 4000) | caps prompt size |
| `tm_outline_enabled` | `system_configs` (default "true") | kill switch — the call spends tokens |

## Restricciones conocidas

- The prompt embeds template hints (arbitrary user content) — keep them
  truncated (`hint_max_chars` slices) so a pathological template can't blow
  the context window.
- Latency adds ~5-10 s per job before slide generation starts; acceptable
  against the per-slide calls that follow.
- This ADR covers only the outline call. The per-slide content call is
  covered by `default-llm-template-merge-content-adr-v2.md`.
