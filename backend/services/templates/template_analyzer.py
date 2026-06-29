"""
template_analyzer.py — Parse a PPTX template into a list of TextSlots.

Each TextSlot describes one text frame that the merge engine will overwrite.
Shapes that are NOT text (images, backgrounds, decorative lines, logos) are
never touched — the analyzer marks them as preserve=True and returns them
as VisualPreserve objects for logging only.

Role inference heuristic (no LLM):
  - Placeholder type PP_PLACEHOLDER.TITLE / PP_PLACEHOLDER.CENTER_TITLE → "title"
  - Placeholder type PP_PLACEHOLDER.SUBTITLE / PP_PLACEHOLDER.BODY → "body"
  - Any other text box in the top 20% of the slide → "title"
  - Any other text box → "body"
  - Small boxes (area < 3% of slide) → "footnote"
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

try:
    from pptx import Presentation
    from pptx.util import Emu
    from pptx.enum.text import PP_ALIGN
    import pptx.oxml.ns as pns
    _PPTX_AVAILABLE = True
except ImportError:
    _PPTX_AVAILABLE = False
    logger.warning("[TemplateAnalyzer] python-pptx not available — analysis will be limited.")


@dataclass
class TextSlot:
    slide_idx: int          # 0-based slide index
    shape_id: int           # shape.shape_id
    shape_name: str
    role: str               # "title" | "body" | "footnote"
    char_limit: int         # estimated max characters for this box
    hint: str               # existing text (used as topic hint for LLM)
    is_placeholder: bool    # True if shape is a PPT placeholder
    placeholder_type: Optional[str] = None


@dataclass
class SlideProfile:
    slide_idx: int
    slide_width_emu: int
    slide_height_emu: int
    slots: List[TextSlot] = field(default_factory=list)
    # Count of non-text shapes (images, backgrounds) preserved untouched
    preserved_shapes: int = 0

    @property
    def hint(self) -> str:
        """Combined text of all title slots — topic hint for content generation."""
        return " / ".join(s.hint for s in self.slots if s.role == "title" and s.hint)


def analyze_template(pptx_path: str) -> List[SlideProfile]:
    """
    Open pptx_path and return one SlideProfile per slide.
    Safe: any per-shape errors are logged and skipped rather than raised.
    """
    if not _PPTX_AVAILABLE:
        raise RuntimeError("python-pptx is required for template analysis.")

    prs = Presentation(pptx_path)
    slide_w = prs.slide_width
    slide_h = prs.slide_height
    slide_area = slide_w * slide_h

    profiles: List[SlideProfile] = []

    for slide_idx, slide in enumerate(prs.slides):
        profile = SlideProfile(
            slide_idx=slide_idx,
            slide_width_emu=int(slide_w),
            slide_height_emu=int(slide_h),
        )

        for shape in slide.shapes:
            try:
                if not shape.has_text_frame:
                    profile.preserved_shapes += 1
                    continue

                tf = shape.text_frame
                existing_text = tf.text.strip()

                role = _infer_role(shape, slide_h, slide_area)
                char_limit = _estimate_char_limit(shape, role)

                slot = TextSlot(
                    slide_idx=slide_idx,
                    shape_id=shape.shape_id,
                    shape_name=shape.name,
                    role=role,
                    char_limit=char_limit,
                    hint=existing_text[:200],
                    is_placeholder=shape.is_placeholder,
                    placeholder_type=_placeholder_type_str(shape),
                )
                profile.slots.append(slot)
            except Exception as exc:
                logger.warning(
                    f"[TemplateAnalyzer] slide {slide_idx} shape '{getattr(shape, 'name', '?')}' skipped: {exc}"
                )
                profile.preserved_shapes += 1

        profiles.append(profile)
        logger.info(
            f"[TemplateAnalyzer] slide {slide_idx}: {len(profile.slots)} text slots, "
            f"{profile.preserved_shapes} preserved shapes."
        )

    return profiles


# ─── private helpers ──────────────────────────────────────────────────────────

def _infer_role(shape, slide_height_emu: int, slide_area_emu: int) -> str:
    if not _PPTX_AVAILABLE:
        return "body"

    if shape.is_placeholder:
        from pptx.enum.shapes import PP_PLACEHOLDER
        try:
            ph_type = shape.placeholder_format.type
            if ph_type in (PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE):
                return "title"
            if ph_type in (PP_PLACEHOLDER.SUBTITLE, PP_PLACEHOLDER.BODY):
                return "body"
        except Exception:
            pass

    try:
        top = shape.top or 0
        width = shape.width or 0
        height = shape.height or 0
        area = width * height

        if area < slide_area_emu * 0.03:
            return "footnote"
        if top < slide_height_emu * 0.20:
            return "title"
    except Exception:
        pass

    return "body"


def _estimate_char_limit(shape, role: str) -> int:
    """
    Rough char limit derived from physical box size.
    title → 80 chars max; footnote → 120; body → derived from area.
    """
    if role == "title":
        return 80
    if role == "footnote":
        return 120

    try:
        # EMU → inches (914400 EMU per inch); ~30 chars per sq inch at 18pt
        w_in = (shape.width or 0) / 914400
        h_in = (shape.height or 0) / 914400
        estimated = int(w_in * h_in * 30)
        return max(80, min(estimated, 600))
    except Exception:
        return 300


def _placeholder_type_str(shape) -> Optional[str]:
    if not shape.is_placeholder:
        return None
    try:
        return str(shape.placeholder_format.type)
    except Exception:
        return None
