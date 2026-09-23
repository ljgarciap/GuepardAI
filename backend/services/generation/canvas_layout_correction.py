"""
canvas_layout_correction.py — Artistic Generation Engine v2.
docs/specs/artistic-generation-v2.md

Deterministic, no-LLM geometry correction for canvas_elements. Shared by:
  - agents/qa_validator.py (ScoreFidelityTool) — estimates real text height
    to detect overlap the LLM's own declared h hides.
  - services/generation/canvas_composer_service.py (compose_canvas_for_job) —
    actually CORRECTS the geometry before it's ever rendered, using the same
    estimate.

Real gap found live (docs/ai/contracts/ — see commit history, not a formal
ADR): a long title wraps to 2 lines but the composer declares an `h` sized
for one, overlapping the text below it. Telling the composer not to overlap
(prompt instruction) and flagging it after the fact (QA judge + deterministic
override) both help, but a live 2-retry test still left 4/17 slides with
the same defect — an LLM cannot reliably self-correct a spatial-layout
mistake through text feedback alone, every attempt. This module fixes the
geometry directly instead of asking the LLM to get it right.
"""
import math
from typing import Any, Dict, List

# Standard 16:9 widescreen deck size in points (13.333in x 7.5in @ 72pt/in) —
# canvas_elements coordinates are percent-of-slide, this converts a percent
# width/a font-pt size into a real character/line estimate.
_SLIDE_WIDTH_PT = 960.0
_SLIDE_HEIGHT_PT = 540.0
# Same factors template_analyzer.py's typographic budget already uses for the
# inverse calculation (box size -> char budget) — reused here for text ->
# real rendered size, not reinvented.
_CHAR_WIDTH_FACTOR = 0.55
_LINE_HEIGHT_FACTOR = 1.25


def estimate_text_height_pct(content: str, size_pt: float, w_pct: float) -> float:
    """Estimate the REAL wrapped height (percent of slide height) of a text
    element from its content length, font size, and box width — the same way
    a renderer actually wraps text, not the LLM's own optimistic guess."""
    if not content or not size_pt or not w_pct:
        return 0.0
    box_width_pt = w_pct / 100.0 * _SLIDE_WIDTH_PT
    chars_per_line = max(1.0, box_width_pt / (size_pt * _CHAR_WIDTH_FACTOR))
    lines = max(1, math.ceil(len(content) / chars_per_line))
    height_pt = lines * size_pt * _LINE_HEIGHT_FACTOR
    return height_pt / _SLIDE_HEIGHT_PT * 100.0


def _x_ranges_overlap(a_x0: float, a_x1: float, b_x0: float, b_x1: float, tolerance: float = 1.0) -> bool:
    return (a_x0 + tolerance) < b_x1 and (b_x0 + tolerance) < a_x1


def auto_correct_overlaps(canvas_elements: Any, gap_pct: float = 0.5) -> Any:
    """
    Expands each text element's declared h to its real estimated wrapped
    height, then pushes down any text element whose original y now falls
    inside a taller element directly above it — but ONLY within the same
    horizontal "column" (text elements whose x-ranges actually overlap).
    Text elements in unrelated columns (e.g. a left body column and a right
    side panel) never affect each other — only genuine vertical stacking
    collisions are corrected, the exact defect class
    agents.qa_validator._summarize_canvas_elements() detects.

    Never touches non-text elements (shape/line/gradient_overlay/image) —
    those aren't part of the "textos solapados" defect this fixes. Returns a
    new list; never mutates the input.
    """
    if not isinstance(canvas_elements, list):
        return canvas_elements

    corrected: List[Dict[str, Any]] = [
        dict(el) if isinstance(el, dict) else el for el in canvas_elements
    ]

    geo: Dict[int, List[float]] = {}  # index -> [x, y, w, real_h]
    for i, el in enumerate(corrected):
        if not isinstance(el, dict) or el.get("type") != "text":
            continue
        try:
            x = float(el.get("x", 0))
            y = float(el.get("y", 0))
            w = float(el.get("w", el.get("size", 0)) or 0)
            h = float(el.get("h", el.get("size", 0)) or 0)
            content = str(el.get("content", el.get("text", "")) or "")
            size = float(el.get("size", 24) or 24)
            real_h = max(h, estimate_text_height_pct(content, size, w))
            geo[i] = [x, y, w, real_h]
        except (TypeError, ValueError):
            continue

    if len(geo) < 2:
        # Still worth applying the single element's own corrected height —
        # a too-short box helps no one even with nothing below it to collide with.
        for i, (x, y, w, real_h) in geo.items():
            corrected[i]["h"] = round(real_h, 2)
        return corrected

    # Group into columns: connected components under x-range overlap.
    remaining = set(geo.keys())
    columns: List[set] = []
    while remaining:
        seed = remaining.pop()
        column = {seed}
        changed = True
        while changed:
            changed = False
            for i in list(remaining):
                xi0, _, wi, _ = geo[i]
                if any(_x_ranges_overlap(xi0, xi0 + wi, geo[j][0], geo[j][0] + geo[j][2]) for j in column):
                    column.add(i)
                    remaining.discard(i)
                    changed = True
        columns.append(column)

    for column in columns:
        ordered = sorted(column, key=lambda i: geo[i][1])  # top to bottom, original y
        cursor = None
        for i in ordered:
            x, y, w, real_h = geo[i]
            if cursor is not None and y < cursor:
                y = cursor
            corrected[i]["y"] = round(y, 2)
            corrected[i]["h"] = round(real_h, 2)
            cursor = y + real_h + gap_pct

    return corrected
