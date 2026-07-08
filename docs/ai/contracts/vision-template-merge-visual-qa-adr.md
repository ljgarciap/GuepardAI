# ADR: Vision LLM call for Template Merge visual QA (v2 Phase 4)

**Date validated**: 2026-07-08 (live `test-ai-request` run — see Validation below)
**Validated by**: AI Architect
**Status**: VALIDATED — new Vision touchpoint, advisory only, default OFF
**Used in**: `services/templates/template_visual_qa.py` — `run_visual_qa()`
**Spec**: `docs/specs/template-merge-v2-quality.md` (Phase 4)
**Design**: `docs/designs/template-merge-v2-quality.md` (§2, optional gated stage)

---

## Decision

After the merged PPTX is rendered, an OPTIONAL pass converts it to images
(LibreOffice → PDF → PyMuPDF, reusing the ingestion pipeline's mechanism)
and sends up to `tm_visual_qa_max_slides` slide images in ONE
`generate_vision_json(prompt, image_paths)` call, asking for per-slide
findings limited to three defect types: `overflow`, `contrast`, `overlap`.

**Advisory, never blocking**: findings are attached to
`TemplateMergeJob.merge_report["visual_qa"]` and surfaced in the UI so the
operator reviews before presenting. The pass NEVER modifies the deck, never
retries generation, and never fails the job (any error → `status:"failed"`
inside the report; missing LibreOffice/PyMuPDF → `status:"unavailable"`).

**Default OFF** (`tm_visual_qa_enabled = "false"`): it spends Vision tokens
per merge — same kill-switch convention as `tm_outline_enabled` and
`auto_data_alignment_enabled`.

**Why one batched call**: N slides in one request keeps cost at 1 call/job
and the model sees the deck as a whole; the per-slide keying in the response
preserves attribution. Slide count is capped by `tm_visual_qa_max_slides`.

## Validation (live test, 2026-07-08)

Two synthetic 1280×720 slide images with deliberate defects, through the
production entry point (`generate_vision_json`, default vision chain):

- **Provider selected**: `pixtral-12b-2409` (first hop of the vision chain)
- **Latency**: ~3.1 s for 2 images
- **Result**: valid JSON, one entry per slide in order. The hard body-text
  overflow was detected with `severity:"high"` and a `detail` quoting the
  exact clipped text; the near-clean control slide returned `findings: []`
  (no false positives).

**Known recall limits (documented, accepted)**: the default vision model did
NOT flag a title clipped by its container box nor a very-low-contrast footer
(#E8E8E8 on white). The touchpoint is reliable for hard overflow — the
highest-value defect after Phase 3's deterministic fit-check — but subtle
contrast/clipping issues may pass silently. If higher recall is ever needed,
route this call to a stronger vision model via the `vision_model` chain in
`system_configs` and re-validate with `test-ai-request` (that would be a new
ADR per jurisdiction rules).

## Request shape

```python
from providers.llm_provider import generate_vision_json

prompt = """You are a meticulous presentation QA reviewer. You receive the slides of a finished corporate deck as images, IN ORDER (image 1 = slide 1, ...).

For each slide, report ONLY defects of these kinds:
- "overflow": text cut off, clipped by its container, or running past the slide/container edges
- "contrast": text hard to read against its background (too little contrast)
- "overlap": text overlapping other text or images

Be conservative: report a finding only when it clearly harms readability or professionalism. A clean slide gets an empty findings list.

Return ONLY a valid JSON object, no markdown fences:
{
  "slides": [
    {"slide": 1, "findings": [{"type": "overflow|contrast|overlap", "severity": "high|medium|low", "detail": "<one line, mention which text>"}]}
  ]
}
Rules:
1. Exactly one entry per slide, in order.
2. findings MUST be [] when the slide is clean.
3. detail must quote or reference the affected text so a human can find it."""

raw = generate_vision_json(prompt, image_paths)   # default vision chain
```

## Response shape (consumed field paths)

```
raw["slides"]                     list, one entry per image sent
raw["slides"][i]["slide"]         int, 1-based
raw["slides"][i]["findings"]      list (empty = clean)
  [j]["type"]                     "overflow" | "contrast" | "overlap"
  [j]["severity"]                 "high" | "medium" | "low"
  [j]["detail"]                   str, references the affected text
```

Parsing is tolerant per-entry (invalid finding dropped, invalid slide entry
dropped); an unusable overall shape → `status:"failed"` in the report.

## Parameters

| Parameter | Value | Reason |
|---|---|---|
| Calls per job | 0 (gate off) or 1 | cost control |
| `tm_visual_qa_enabled` | `system_configs` (default `"false"`) | spends Vision tokens |
| `tm_visual_qa_max_slides` | `system_configs` (default 15) | caps payload/cost |
| Image scale | 2.0 (PyMuPDF matrix, same as `artistic_essence_service`) | proven readable resolution |
| `model` | not set — default vision chain from `system_configs` | never hardcoded |

## Restricciones conocidas

- Requires LibreOffice + PyMuPDF in the runtime (both in the Docker image;
  absent locally → `status:"unavailable"`, job unaffected).
- The findings are advisory text for a human; nothing downstream parses
  them for automated rework (a rework loop would be a new design + ADR).
- Recall limits above: do not present this gate as a guarantee of a
  defect-free deck.
