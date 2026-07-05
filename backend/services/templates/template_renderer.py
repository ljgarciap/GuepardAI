"""
template_renderer.py — In-place PPTX editor for the Template Merge Engine.

Opens a COPY of the template (the original is never modified), replaces the
text of every slot identified by TemplateAnalyzer with the LLM-generated
content, and saves the result to output_path.

Visual structure is fully preserved:
  - All images, backgrounds, shapes without text → untouched
  - Formatting is preserved by copying the <a:rPr> XML element from the first
    non-empty run of each text frame into each replacement run.  This approach
    preserves ALL formatting attributes — font name, size, bold, italic, color
    (both explicit RGB and theme colors), character spacing, etc. — without
    having to enumerate each attribute individually.
  - Shapes not in content_map are never touched.
  - Empty replacement strings are skipped — the original text is kept.
"""
import logging
import os
import re
import shutil
from typing import Dict, List

from services.templates.template_analyzer import SlideProfile

logger = logging.getLogger(__name__)

try:
    from pptx import Presentation
    from pptx.util import Pt
    from pptx.oxml.ns import qn
    from lxml import etree
    _PPTX_AVAILABLE = True
except ImportError:
    _PPTX_AVAILABLE = False


def render_merged_pptx(
    template_path: str,
    profiles: List[SlideProfile],
    slide_contents: List[Dict[int, str]],
    output_path: str,
) -> str:
    """
    Copy template → inject content → save to output_path.
    Returns output_path on success. Raises on fatal error.

    `slide_contents` must be parallel to `profiles` (same length).
    Each element is a dict: shape_id (int) → text string.
    """
    if not _PPTX_AVAILABLE:
        raise RuntimeError("python-pptx is required for template rendering.")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Work on a copy — the template asset is immutable
    shutil.copy2(template_path, output_path)

    prs = Presentation(output_path)

    if len(profiles) != len(slide_contents):
        logger.warning(
            f"[TemplateMergeRenderer] profiles/contents length mismatch "
            f"({len(profiles)} vs {len(slide_contents)}) — proceeding with min."
        )

    for profile, content_map in zip(profiles, slide_contents):
        if not content_map:
            continue

        slide = prs.slides[profile.slide_idx]
        _inject_slide_content(slide, content_map, profile.slide_idx)

    prs.save(output_path)
    logger.info(f"[TemplateMergeRenderer] Saved merged PPTX to: {output_path}")
    return output_path


# ─── private ──────────────────────────────────────────────────────────────────

def _inject_slide_content(slide, content_map: Dict[int, str], slide_idx: int) -> None:
    """Iterate the slide's shapes; for each shape in content_map, replace text."""
    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        new_text = content_map.get(shape.shape_id)
        if new_text is None:
            continue
        # Strip markdown defensively (belt-and-suspenders with template_content)
        new_text = _strip_markdown(new_text.strip())
        if not new_text:
            # Empty replacement → keep original template text
            continue
        try:
            _replace_text_frame(shape.text_frame, new_text)
        except Exception as exc:
            logger.warning(
                f"[TemplateMergeRenderer] slide {slide_idx} shape {shape.shape_id} "
                f"'{shape.name}' text injection failed: {exc}"
            )


def _replace_text_frame(tf, new_text: str) -> None:
    """
    Replace all text in tf with new_text while preserving ALL formatting.

    Strategy:
      1. Capture <a:rPr> XML from the first non-empty run — this preserves
         font, size, bold, italic, color (RGB and theme), character spacing, etc.
      2. Clear every run from the first paragraph.
      3. Add a single new run with the captured <a:rPr> and the new text.
      4. Clear all remaining paragraphs (keep XML structure for slide geometry).

    If new_text contains newlines, each line becomes a separate run separated
    by a soft line-break element (<a:br>) so the visual layout is preserved.
    """
    paragraphs = tf.paragraphs
    if not paragraphs:
        return

    base_rpr = _capture_base_rpr(tf)

    first_para = paragraphs[0]

    # Build content: split on newlines → runs separated by <a:br>
    lines = [l for l in new_text.split('\n') if l.strip()]
    if not lines:
        lines = [new_text]

    _set_paragraph_text(first_para, lines, base_rpr)

    # Clear remaining paragraphs — keep them so shape geometry stays stable
    for para in list(paragraphs)[1:]:
        _clear_paragraph(para)


def _capture_base_rpr(tf):
    """
    Return a standalone copy of the <a:rPr> element from the first non-empty run.
    Returns None if no explicit run properties are found (formatting then inherits
    from the paragraph/shape theme, which is preserved automatically).
    """
    for para in tf.paragraphs:
        for run in para.runs:
            if run.text.strip():
                rpr_elem = run._r.find(qn('a:rPr'))
                if rpr_elem is not None:
                    # etree.fromstring(tostring(...)) creates an orphan deep copy
                    return etree.fromstring(etree.tostring(rpr_elem))
    return None


def _set_paragraph_text(para, lines: List[str], base_rpr) -> None:
    """
    Clear existing runs and write `lines` into `para`.

    Each line becomes an <a:r> run; lines are separated by <a:br> (soft return)
    so the vertical spacing stays compact within the original paragraph frame.
    Each run gets a copy of `base_rpr` to preserve formatting.
    """
    p_elem = para._p

    # Remove all existing runs and soft-breaks
    for elem in p_elem.findall(qn('a:r')):
        p_elem.remove(elem)
    for elem in p_elem.findall(qn('a:br')):
        p_elem.remove(elem)

    for i, line_text in enumerate(lines):
        if i > 0:
            # Insert a soft line-break before subsequent lines
            br_elem = etree.SubElement(p_elem, qn('a:br'))
            if base_rpr is not None:
                br_elem.append(etree.fromstring(etree.tostring(base_rpr)))

        run = para.add_run()
        run.text = line_text

        if base_rpr is not None:
            r_elem = run._r
            existing_rpr = r_elem.find(qn('a:rPr'))
            if existing_rpr is not None:
                r_elem.remove(existing_rpr)
            r_elem.insert(0, etree.fromstring(etree.tostring(base_rpr)))


def _clear_paragraph(para) -> None:
    """Remove all runs and soft-breaks from a paragraph, leaving it empty."""
    p_elem = para._p
    for elem in p_elem.findall(qn('a:r')):
        p_elem.remove(elem)
    for elem in p_elem.findall(qn('a:br')):
        p_elem.remove(elem)


def _strip_markdown(text: str) -> str:
    """Defensive strip of markdown formatting in case LLM ignored instructions."""
    if not text:
        return text
    text = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'_{1,2}(.+?)_{1,2}', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[\-\*\+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    return text.strip()
