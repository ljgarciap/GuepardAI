"""
template_renderer.py — In-place PPTX editor for the Template Merge Engine.

Opens a COPY of the template (the original is never modified), replaces the
text of every slot identified by TemplateAnalyzer with the LLM-generated
content, and saves the result to output_path.

Visual structure is fully preserved:
  - All images, backgrounds, shapes without text → untouched
  - Font family, font size, bold/italic, color, alignment → preserved from
    the first run of each paragraph (only the text string changes)
  - If the slot has multiple paragraphs/runs, all content is collapsed into
    a single paragraph with the first run's formatting, then the remaining
    paragraphs are cleared.  This keeps the slide visually stable.
"""
import logging
import os
import shutil
from typing import Dict, List

from services.templates.template_analyzer import SlideProfile

logger = logging.getLogger(__name__)

try:
    from pptx import Presentation
    from pptx.util import Pt
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
        try:
            _replace_text_frame(shape.text_frame, str(new_text))
        except Exception as exc:
            logger.warning(
                f"[TemplateMergeRenderer] slide {slide_idx} shape {shape.shape_id} "
                f"'{shape.name}' text injection failed: {exc}"
            )


def _replace_text_frame(tf, new_text: str) -> None:
    """
    Replace all text in tf with new_text while preserving the formatting of
    the first run of the first non-empty paragraph.

    Strategy:
      1. Capture formatting from the first available run (font name, size,
         bold, italic, color).
      2. Clear every paragraph's runs.
      3. Write new_text into the first paragraph's first run.
      4. Clear all remaining paragraphs (keep XML structure but empty text).

    This avoids touching any XML attributes unrelated to text (geometry,
    position, word-wrap settings, etc.).
    """
    paragraphs = tf.paragraphs
    if not paragraphs:
        return

    # Capture base formatting from the first run found anywhere in the frame
    base_font = _capture_base_font(tf)

    new_text = new_text.strip()

    # Write the new text into the first paragraph
    first_para = paragraphs[0]
    _set_paragraph_text(first_para, new_text, base_font)

    # Clear remaining paragraphs (preserve them so slide geometry is stable)
    for para in list(paragraphs)[1:]:
        _clear_paragraph(para)


def _capture_base_font(tf):
    """Return a dict of font attributes from the first non-empty run."""
    for para in tf.paragraphs:
        for run in para.runs:
            if run.text.strip():
                font = run.font
                return {
                    "name": font.name,
                    "size": font.size,
                    "bold": font.bold,
                    "italic": font.italic,
                    "color_rgb": _safe_color(font),
                }
    return {}


def _safe_color(font):
    try:
        if font.color and font.color.type is not None:
            return font.color.rgb
    except Exception:
        pass
    return None


def _set_paragraph_text(para, text: str, base_font: dict) -> None:
    """Clear existing runs and add a single run with text + preserved formatting."""
    # Remove all existing runs from XML
    from pptx.oxml.ns import qn
    p_elem = para._p
    for r in p_elem.findall(qn("a:r")):
        p_elem.remove(r)

    # Add a new run
    run = para.add_run()
    run.text = text

    if base_font:
        font = run.font
        if base_font.get("name"):
            try:
                font.name = base_font["name"]
            except Exception:
                pass
        if base_font.get("size"):
            try:
                font.size = base_font["size"]
            except Exception:
                pass
        if base_font.get("bold") is not None:
            try:
                font.bold = base_font["bold"]
            except Exception:
                pass
        if base_font.get("italic") is not None:
            try:
                font.italic = base_font["italic"]
            except Exception:
                pass
        if base_font.get("color_rgb"):
            try:
                from pptx.dml.color import RGBColor
                font.color.rgb = base_font["color_rgb"]
            except Exception:
                pass


def _clear_paragraph(para) -> None:
    """Remove all runs from a paragraph, leaving an empty paragraph element."""
    from pptx.oxml.ns import qn
    p_elem = para._p
    for r in p_elem.findall(qn("a:r")):
        p_elem.remove(r)
