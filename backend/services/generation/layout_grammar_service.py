"""
layout_grammar_service.py — Deterministic geometry extraction + clustering for
Artistic Generation Engine v2's grammar mining (Phase 0).
docs/specs/artistic-generation-v2.md

Two source formats feed one uniform structure (MinedRegion, percent-of-page
geometry, same coordinate space as canvas_elements) so MineLayoutGrammarTool
(agents/mine_layout_grammar.py) never branches on file type:

  - PPTX: reuses services/templates/template_analyzer.py::analyze_template()
    for text regions — real reuse of the Template Merge Engine's shape
    traversal (role inference, area filtering), none of it reimplemented.
    Non-text shape geometry (decorative rects, icons) isn't captured by that
    traversal (it only walks shapes with a text frame) — PPTX mining input is
    text-slot geometry only for now.
  - PDF: new extraction via PyMuPDF (already a project dependency, already
    used the same way — same library, same doc.open() pattern — in
    services/ingestion/visual_dna_service.py::extract_pdf_dna() for
    font/color; this adds the per-region geometry that function never
    needed). Text blocks, image rects, and vector drawings (the ribbon
    bands, donut-ring strokes real brand decks use for decoration).

Clustering here is deterministic (no LLM call) — it groups pages/slides that
repeat the same rough region layout into one cluster. MineLayoutGrammarTool
takes these clusters and does the one LLM call this phase needs: naming and
classifying each cluster into a BrandLayoutGrammar signature.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from providers.llm_provider import get_system_config


@dataclass
class LayoutMiningConfig:
    min_shape_area_pct: float = 0.3
    max_shape_area_pct: float = 85.0
    geometry_cluster_tolerance_pct: float = 4.0

    @classmethod
    def from_db(cls) -> "LayoutMiningConfig":
        return cls(
            min_shape_area_pct=float(get_system_config("layout_mining_min_shape_area_pct", "0.3")),
            max_shape_area_pct=float(get_system_config("layout_mining_max_shape_area_pct", "85.0")),
            geometry_cluster_tolerance_pct=float(get_system_config("layout_mining_cluster_tolerance_pct", "4.0")),
        )


@dataclass
class MinedRegion:
    page_idx: int
    region_type: str            # "text" | "image" | "shape"
    x_pct: float
    y_pct: float
    w_pct: float
    h_pct: float
    role: Optional[str] = None       # "title" | "body" | "footnote" (text only)
    text_hint: Optional[str] = None
    color: Optional[str] = None      # fill/stroke hex (shapes only)


def extract_pptx_regions(pptx_path: str) -> List[MinedRegion]:
    """Text-slot geometry via the existing Template Merge analyzer — no new
    traversal logic. Slots without resolvable geometry (x_pct is None — see
    template_analyzer.py::_geometry_pct) are skipped."""
    from services.templates.template_analyzer import analyze_template
    from services.templates.template_config import TemplateMergeConfig

    profiles = analyze_template(pptx_path, TemplateMergeConfig())
    regions: List[MinedRegion] = []
    for profile in profiles:
        for slot in profile.slots:
            if slot.x_pct is None:
                continue
            regions.append(MinedRegion(
                page_idx=profile.slide_idx,
                region_type="text",
                x_pct=slot.x_pct, y_pct=slot.y_pct, w_pct=slot.w_pct, h_pct=slot.h_pct,
                role=slot.role,
                text_hint=slot.hint,
            ))
    return regions


def extract_pdf_regions(pdf_path: str, config: Optional[LayoutMiningConfig] = None) -> List[MinedRegion]:
    """PyMuPDF-based geometry extraction: text blocks, image rects, vector
    drawings. New code (visual_dna_service.py's PDF path never needed
    per-region geometry, only font/color and image presence)."""
    import fitz  # PyMuPDF

    cfg = config or LayoutMiningConfig.from_db()
    doc = fitz.open(pdf_path)
    regions: List[MinedRegion] = []

    try:
        for page_idx, page in enumerate(doc):
            # page.rect is the DISPLAY-orientation size (post-rotation) — the one
            # a viewer/renderer actually sees. get_text()/get_image_rects()/
            # get_drawings() all return coordinates in the page's RAW/mediabox
            # space, which differs from page.rect whenever page.rotation != 0
            # (confirmed empirically on the real Embonor sample, a 90°-rotated
            # PDF: raw rects reach ~130% of page.rect's height if normalized
            # without correction). page.rotation_matrix maps raw -> display
            # space; every rect must be transformed through it before computing
            # percentages, or a landscape deck's mined geometry comes out both
            # out-of-bounds AND semantically transposed (top becomes left).
            page_w, page_h = page.rect.width, page.rect.height
            if not page_w or not page_h:
                continue
            page_area = page_w * page_h
            rot = page.rotation_matrix

            for block in page.get_text("dict").get("blocks", []):
                bbox = block.get("bbox")
                if not bbox:
                    continue
                text = "".join(
                    span.get("text", "")
                    for line in block.get("lines", [])
                    for span in line.get("spans", [])
                ).strip()
                if not text:
                    continue
                r = fitz.Rect(bbox) * rot
                area_pct = (r.width * r.height) / page_area * 100
                role = (
                    "title" if r.y0 < page_h * 0.20
                    else "footnote" if area_pct < 3.0
                    else "body"
                )
                regions.append(MinedRegion(
                    page_idx=page_idx, region_type="text",
                    x_pct=_clamp_pct(r.x0 / page_w * 100), y_pct=_clamp_pct(r.y0 / page_h * 100),
                    w_pct=_clamp_pct(r.width / page_w * 100), h_pct=_clamp_pct(r.height / page_h * 100),
                    role=role, text_hint=text[:200],
                ))

            for img in page.get_images(full=True):
                xref = img[0]
                try:
                    rects = page.get_image_rects(xref)
                except Exception:
                    continue
                for raw_rect in rects:
                    r = raw_rect * rot
                    area_pct = (r.width * r.height) / page_area * 100
                    if area_pct < cfg.min_shape_area_pct or area_pct > cfg.max_shape_area_pct:
                        continue
                    regions.append(MinedRegion(
                        page_idx=page_idx, region_type="image",
                        x_pct=_clamp_pct(r.x0 / page_w * 100), y_pct=_clamp_pct(r.y0 / page_h * 100),
                        w_pct=_clamp_pct(r.width / page_w * 100), h_pct=_clamp_pct(r.height / page_h * 100),
                    ))

            try:
                drawings = page.get_drawings()
            except Exception:
                drawings = []
            for drawing in drawings:
                raw_rect = drawing.get("rect")
                if not raw_rect:
                    continue
                r = raw_rect * rot
                area_pct = (r.width * r.height) / page_area * 100
                if area_pct < cfg.min_shape_area_pct or area_pct > cfg.max_shape_area_pct:
                    continue
                fill = drawing.get("fill")
                color_hex = _rgb_to_hex(fill)
                if fill is not None and _is_near_invisible(fill):
                    continue
                regions.append(MinedRegion(
                    page_idx=page_idx, region_type="shape",
                    x_pct=_clamp_pct(r.x0 / page_w * 100), y_pct=_clamp_pct(r.y0 / page_h * 100),
                    w_pct=_clamp_pct(r.width / page_w * 100), h_pct=_clamp_pct(r.height / page_h * 100),
                    color=color_hex,
                ))
    finally:
        doc.close()

    return regions


def cluster_regions(regions: List[MinedRegion], config: Optional[LayoutMiningConfig] = None) -> List[dict]:
    """Group regions that repeat across pages/slides with near-identical
    geometry into named clusters — the raw signal MineLayoutGrammarTool's LLM
    call names and classifies. Purely deterministic, no LLM call here.

    Region-level, not page-level: matching a WHOLE page's entire region set
    against another page's is too strict for real decks — one extra caption or
    a slightly different decorative flourish on an otherwise-identical KPI
    slide would prevent any match at all. Empirically confirmed against the
    real Embonor sample (docs/specs/artistic-generation-v2.md's Insumos):
    a whole-page-signature approach found only 1 repeating cluster across 27
    pages despite the deck's real, visually obvious donut-KPI-trio pattern.
    Clustering individual regions first (by rounded type+role+x/y/w/h
    signature — bucketing by `geometry_cluster_tolerance_pct` absorbs small
    extraction jitter), then merging clusters that share the exact same page
    set into one multi-slot signature, is robust to that per-page noise.
    """
    cfg = config or LayoutMiningConfig.from_db()

    by_signature: Dict[tuple, Dict[str, object]] = {}
    for region in regions:
        sig = (
            region.region_type, region.role or "",
            _bucket(region.x_pct, cfg), _bucket(region.y_pct, cfg),
            _bucket(region.w_pct, cfg), _bucket(region.h_pct, cfg),
        )
        entry = by_signature.setdefault(sig, {"regions": [], "page_indices": set()})
        entry["regions"].append(region)
        entry["page_indices"].add(region.page_idx)

    # Keep signals worth naming: repeats across >=2 pages, or a large-enough
    # single occurrence to be a salient one-off motif (e.g. a cover banner) —
    # not every tiny single-page region, or noise dominates the cluster count.
    kept = [
        entry for entry in by_signature.values()
        if len(entry["page_indices"]) >= 2
        or (entry["regions"][0].w_pct * entry["regions"][0].h_pct) >= 5.0
    ]

    # Merge region-clusters that repeat on the EXACT same set of pages into one
    # multi-slot signature — independently-repeating regions sharing a page set
    # are very likely slots of the same layout (e.g. 3 KPI icon-centers that
    # each recur on pages 4/9/14 are one "KPI trio" signature, not three).
    merged: Dict[frozenset, List[Dict[str, object]]] = {}
    for entry in kept:
        merged.setdefault(frozenset(entry["page_indices"]), []).append(entry)

    clusters = []
    for page_set, entries in merged.items():
        clusters.append({
            "page_indices": sorted(page_set),
            "shared_slots": [
                {
                    "role": entry["regions"][0].role or entry["regions"][0].region_type,
                    "region_type": entry["regions"][0].region_type,
                    "x_pct": entry["regions"][0].x_pct, "y_pct": entry["regions"][0].y_pct,
                    "w_pct": entry["regions"][0].w_pct, "h_pct": entry["regions"][0].h_pct,
                    "text_hint": entry["regions"][0].text_hint,
                    "color": entry["regions"][0].color,
                }
                for entry in entries
            ],
        })
    return clusters


def _bucket(value: float, cfg: LayoutMiningConfig) -> float:
    tol = cfg.geometry_cluster_tolerance_pct or 1.0
    return round(value / tol) * tol


def _clamp_pct(value: float) -> float:
    """Glyph/vector bboxes occasionally overshoot the page edge by a fraction
    of a percent (font metrics, anti-aliasing) — clamp to keep every mined
    region in the same [0,100] space canvas_elements expects, rather than
    letting sub-1% noise become an "out of bounds" false positive later."""
    return round(max(0.0, min(100.0, value)), 2)


def _rgb_to_hex(rgb) -> Optional[str]:
    try:
        r, g, b = rgb
        return f"#{int(round(r * 255)):02X}{int(round(g * 255)):02X}{int(round(b * 255)):02X}"
    except (TypeError, ValueError):
        return None


def _is_near_invisible(rgb) -> bool:
    try:
        r, g, b = rgb
        return (r + g + b) / 3 > 0.97
    except (TypeError, ValueError):
        return False
