"""
template_visual_qa.py — Optional Vision-LLM QA pass for merged decks (v2 Phase 4).

Converts the merged PPTX to images (LibreOffice → PDF → PyMuPDF, the same
mechanism the ingestion pipeline uses) and asks a Vision LLM to flag visual
defects — overflow, low contrast, overlap — per slide. Findings are ADVISORY:
they are attached to the job's merge_report for the operator to review; the
pass never modifies the deck and never fails the job.

Gated by system_configs.tm_visual_qa_enabled (default OFF — spends Vision
tokens). ADR: docs/ai/contracts/vision-template-merge-visual-qa-adr.md.

run_visual_qa() never raises:
  None                        → gate off (nothing to report)
  {"status": "ok", ...}       → pass ran; findings (possibly zero) inside
  {"status": "unavailable"}   → LibreOffice/PyMuPDF missing in this runtime
  {"status": "failed", ...}   → conversion or Vision call broke; job unaffected
"""
import logging
import os
import shutil
import tempfile
from typing import List, Optional

from providers.llm_provider import generate_vision_json
from services.templates.template_config import TemplateMergeConfig

logger = logging.getLogger(__name__)

FINDING_TYPES = ("overflow", "contrast", "overlap")
SEVERITIES = ("high", "medium", "low")

_PROMPT = """You are a meticulous presentation QA reviewer. You receive the slides of a finished corporate deck as images, IN ORDER (image 1 = slide 1, image 2 = slide 2, ...).

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


def run_visual_qa(pptx_path: str, config: TemplateMergeConfig) -> Optional[dict]:
    """Advisory Vision QA over the merged deck. Never raises."""
    if not config.visual_qa_enabled:
        return None

    tmp_dir = tempfile.mkdtemp(prefix="tm_vqa_")
    try:
        pdf_path = _to_pdf(pptx_path, tmp_dir)
        if not pdf_path:
            return {"status": "unavailable",
                    "detail": "PPTX→PDF conversion not available in this runtime (LibreOffice)."}

        image_paths = _pdf_to_images(pdf_path, tmp_dir, config.visual_qa_max_slides)
        if not image_paths:
            return {"status": "unavailable",
                    "detail": "PDF→image rendering not available in this runtime (PyMuPDF)."}

        raw = generate_vision_json(_PROMPT, image_paths)
        report = _parse_findings(raw, len(image_paths))
        if report is None:
            return {"status": "failed", "detail": "Vision response had no usable slide findings."}

        report["status"] = "ok"
        report["slides_reviewed"] = len(image_paths)
        logger.info(
            f"[TemplateVisualQA] {report['total_findings']} finding(s) across "
            f"{len(image_paths)} slide(s)."
        )
        return report
    except Exception as exc:
        logger.warning(f"[TemplateVisualQA] pass failed (job unaffected): {exc}")
        return {"status": "failed", "detail": str(exc)[:500]}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ─── private ──────────────────────────────────────────────────────────────────

def _to_pdf(pptx_path: str, out_dir: str) -> Optional[str]:
    """LibreOffice conversion, reusing the ingestion pipeline's helper."""
    from services.ingestion.ingestion_orchestrator import convert_pptx_to_pdf
    return convert_pptx_to_pdf(pptx_path, out_dir)


def _pdf_to_images(pdf_path: str, out_dir: str, max_slides: int) -> List[str]:
    """PDF pages → PNGs at 2.0 scale (same resolution the ingestion Vision uses)."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return []

    paths: List[str] = []
    doc = fitz.open(pdf_path)
    try:
        for idx, page in enumerate(doc):
            if idx >= max_slides:
                break
            pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
            path = os.path.join(out_dir, f"slide_{idx + 1}.png")
            pix.save(path)
            paths.append(path)
    finally:
        doc.close()
    return paths


def _parse_findings(raw, slides_sent: int) -> Optional[dict]:
    """
    Tolerant parsing: invalid findings/entries are dropped; an unusable
    overall shape returns None (caller reports status "failed").
    """
    if not isinstance(raw, dict):
        return None
    slides_raw = raw.get("slides")
    if not isinstance(slides_raw, list):
        return None

    slides = []
    total = 0
    for entry in slides_raw:
        try:
            if not isinstance(entry, dict):
                continue
            number = int(entry.get("slide"))
            if not (1 <= number <= slides_sent):
                continue
            findings = []
            for f in entry.get("findings") or []:
                if not isinstance(f, dict):
                    continue
                ftype = str(f.get("type", "")).strip().lower()
                severity = str(f.get("severity", "")).strip().lower()
                detail = str(f.get("detail", "")).strip()
                if ftype in FINDING_TYPES and detail:
                    findings.append({
                        "type": ftype,
                        "severity": severity if severity in SEVERITIES else "medium",
                        "detail": detail[:300],
                    })
            slides.append({"slide": number, "findings": findings})
            total += len(findings)
        except Exception:
            continue

    if not slides:
        return None
    return {"slides": slides, "total_findings": total}
