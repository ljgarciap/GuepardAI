# ADR: Default-routed LLM call for Template Merge slide content generation

**Date validated**: 2026-07-04 (backfill — touchpoint has been live in production since 2026-06-29, commit `8e481ab`, without a prior ADR)
**Validated by**: AI Architect (retroactive code + test-suite review — no fresh live API call; see Validation note below)
**Status**: SUPERSEDED (2026-07-07) by `default-llm-template-merge-content-adr-v2.md` — the v2 Phase 2 prompt adds deck-plan context, previous-slide summaries, language pinning and plan-derived RAG queries
**Used in**: Template Merge Engine — `services/templates/template_content.py:106`

---

## Decision

`_generate_for_slide()` calls `generate_json(prompt)` from
`providers/llm_provider.py` with **no `specialization` argument** — it uses
default routing (`ACTIVE_LLM` env var → Mistral → Gemini → OpenAI fallback
chain), the same routing used by the Redactor's `SlideContentTool` for
regular presentation content synthesis.

**Why default routing and not `specialization="design"`**: this call
generates prose/bullet *content* from RAG context, not a visual/layout
decision. `specialization="design"` is reserved for calls that need Claude's
specific design judgment (art direction, layout composition) per
`providers/llm_provider.py`'s `resolve_provider()`. Content synthesis calls
elsewhere in the codebase (Redactor) follow the same default-routing
convention — this call is consistent with existing precedent, not a new
pattern.

No new provider, no new model, no new vector dimension — this ADR exists
because every AI touchpoint requires one per `.claude/agents/ai-architect.md`
jurisdiction rules, and this one had never been written down.

---

## Validation note (why this isn't a fresh live test)

The AI Architect's normal process (`test-ai-request` skill) is to make a real
API call before validating a new touchpoint. This touchpoint is **not new** —
it has been running in production since 2026-06-29 using the exact same
`generate_json()` entry point already validated for every other content-generation
call in the codebase. Re-testing an already-proven call path would spend
tokens without producing new information. Instead, this ADR is validated by:

1. Static confirmation that the call goes through `providers/llm_provider.py`
   (no direct provider SDK import) — grep-verified in
   `docs/designs/template-merge.md`.
2. The behavioral contract below is now enforced by
   `backend/tests/test_template_merge.py` (mocked `generate_json`, 8 tests
   covering the request/response shape, truncation, and error handling) and
   `backend/tests/test_template_merge_integration.py` (full pipeline against
   a real generated `.pptx`).

If `ACTIVE_LLM` changes to a provider not yet exercised against this specific
prompt shape, a normal live test via `test-ai-request` should be run before
relying on it in production — this ADR does not certify every provider in
the fallback chain, only the routing mechanism.

---

## Request shape

```python
from providers.llm_provider import generate_json

prompt = """You are a corporate presentation writer. Write content for slide {slide_num} of {total_slides}.

USER INTENT: {user_prompt}

SLIDE TOPIC HINT (from template): {topic_hint}

KNOWLEDGE CONTEXT (from document):
{rag_context}

SLIDE SLOTS TO FILL:
  shape_id={id} role="title|body|footnote" action="preserve|adapt|rewrite" char_limit={n} hint="{existing text}"

STRICT FORMAT RULES:
1. Return ONLY a flat JSON object: {"shape_id_string": "text content", ...}
2. All values MUST be plain strings — never nest objects
3. NO markdown
4. Respect char_limit strictly
...

Respond with ONLY valid JSON — no markdown fences, no extra text."""

raw = generate_json(prompt)  # no specialization= → default routing
```

## Response shape

```
raw: Dict[str, str]   # keyed by shape_id as a string, e.g. {"42": "Generated text"}
```

**Observed provider deviation**: some providers occasionally nest the value
instead of returning a flat string, e.g. `{"42": {"role": "body", "content": "..."}}`
or even a stringified dict `{"42": "{'role': 'body', 'content': '...'}"}`.
`_unwrap_value()` handles all three shapes (dict with known key, list of
bullet items, `ast.literal_eval` on a dict-looking string) before falling
back to the raw string.

## Parameters

| Parameter | Value | Reason |
|---|---|---|
| `specialization` | not set (default routing) | content synthesis, not design/layout judgment |
| `model` | whatever `resolve_provider()` picks for default routing | never hardcoded — respects `ACTIVE_LLM` |
| Calls per job | 1 per slide with ≥1 non-preserved slot | slides with only `preserve` slots skip the LLM entirely |
| `rag_context_max_chars` | from `system_configs.tm_rag_context_max_chars` (default 3000) | caps prompt size |
| `rag_k` | from `system_configs.tm_rag_k` (default 6) | RAG chunks retrieved per slide |

## Restricciones conocidas

- Rate limits / context window: inherited from whichever provider
  `resolve_provider()` selects — not pinned to a specific model's limits by
  this feature.
- Per-slide failures (LLM or RAG) are caught and degrade to empty strings —
  they do not raise, do not retry, and do not abort the job.
- This ADR does not cover the Vision LLM touchpoint used elsewhere in
  ingestion (`brand_analyst.py`) — that has its own contract.

## Notas

If `template_content.py` is ever changed to force
`specialization="design"` (e.g. because slide content needs to reflect
visual/layout constraints, not just text), that is a routing change and
requires a new ADR — per `ai-architect.md` jurisdiction: "Any call structure
that differs from the last validated ADR for that provider."
