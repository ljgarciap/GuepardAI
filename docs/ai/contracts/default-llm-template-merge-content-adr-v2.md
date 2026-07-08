# ADR v2: Default-routed LLM call for Template Merge slide content generation

**Date validated**: 2026-07-07
**Validated by**: AI Architect
**Status**: VALIDATED — supersedes `default-llm-template-merge-content-adr.md` (v1)
**Used in**: `services/templates/template_content.py` — `_generate_for_slide()`
**Spec**: `docs/specs/template-merge-v2-quality.md` (Phase 2)

---

## What changed vs. v1 (why a new ADR)

Per `ai-architect.md` jurisdiction, a call structure that differs from the
last validated ADR requires a new one. The routing is UNCHANGED (default
routing via `generate_json`, no `specialization`); the prompt structure
gains four elements:

1. **Deck plan context** — the slide's `topic` + `key_points` + deck `tone`
   from the outline call (see `default-llm-template-merge-outline-adr.md`).
   Only present when the plan succeeded; absent → prompt degrades to the v1
   shape.
2. **Previous-slide summaries** — one line per already-generated slide
   ("Slide N: <first generated text, truncated>") with an explicit
   do-not-repeat instruction.
3. **Language pinning** — "Write ALL content in {language}" from the plan;
   fallback instruction "same language as the USER INTENT" when no plan.
4. **RAG query source** — the retrieval query is the plan's per-slide
   `rag_query` (fallback: v1's template-hint query). RAG chunks already
   used verbatim by a previous slide are de-prioritized (moved to the end
   of the context, dropped first by the char cap).

Slot description, strict-format rules, flat-JSON response keyed by slot_key
strings ("42", "42/17", "42:r2c3"), `_unwrap_value()` tolerance, markdown
stripping, and word-boundary truncation all remain as in v1/Phase 1.

## Validation note

The routing mechanism and response handling are unchanged and covered by
the v1 validation plus the Phase 1/Phase 2 test suites (mocked). The NEW
structural elements ride the same `generate_json` entry point that was
live-validated today for the outline call (same provider chain, same JSON
contract style, live pair recorded in the outline ADR) — a second live call
for the same mechanism would spend tokens without new information. If
`ACTIVE_LLM` moves to a provider not yet exercised, run `test-ai-request`
against this prompt shape before relying on it.

## Request shape (Phase 2)

```python
raw = generate_json(prompt)   # no specialization= → default routing

# prompt = v1 sections (USER INTENT / SLIDE TOPIC HINT / KNOWLEDGE CONTEXT /
# SLIDE SLOTS / STRICT FORMAT RULES) plus, when available:
#
# DECK PLAN (follow it):
#   Deck tone: {tone}
#   This slide's topic: {topic}
#   Key points to communicate: - {kp1} - {kp2} ...
#
# PREVIOUS SLIDES (do NOT repeat their points):
#   Slide 1: {summary}
#   ...
#
# LANGUAGE: Write ALL content in "{language}".
```

## Response shape

Unchanged from v1: flat `Dict[str, str]` keyed by slot_key strings.

## Parameters

| Parameter | Value | Reason |
|---|---|---|
| `specialization` | not set (default routing) | content synthesis, not design judgment |
| Calls per job | 1 per slide with ≥1 non-preserved slot (unchanged) | slides with only preserved slots skip the LLM |
| `tm_rag_k` / `tm_rag_context_max_chars` | unchanged (6 / 3000) | per-slide retrieval budget |
| Prev-summary length | first 100 chars of the slide's first generated value | keeps prompt growth linear and small |

## Restricciones conocidas

- Per-slide failures still degrade to `None` for the slide (originals kept,
  reported `failed`) — never abort the job.
- Prompt size now grows ~1 line per previous slide; for very long decks the
  summaries section is the first candidate to cap if context pressure
  appears (not needed at current deck sizes).
- The planned Phase 3 shorten-retry variant (regenerate an overflowing slot
  with a tighter limit) is covered by this ADR in advance: same routing,
  same response contract, stricter char budget in the prompt.
