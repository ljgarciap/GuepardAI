"""
template_content.py — Generate text content for each slide of a template.

One LLM call per slide (not per slot), returning a JSON dict keyed by
shape_id → text string (or list of strings for bullet-style body slots).

RAG strategy: for each slide, query the knowledge base using the slide's
existing text as the search query. Falls back to the user prompt + slide
number when the existing text is too short to be meaningful.
"""
import json
import logging
from typing import Dict, List

from providers.llm_provider import generate_json
from services.generation.content_service import search_rag
from services.templates.template_analyzer import SlideProfile, TextSlot

logger = logging.getLogger(__name__)

_FALLBACK_CHARS = 300
_RAG_K = 6


def generate_slide_contents(
    profiles: List[SlideProfile],
    knowledge_filename: str,
    brand_id: int,
    user_prompt: str,
) -> List[Dict[int, str]]:
    """
    Returns a list parallel to `profiles`: each element is a dict mapping
    shape_id (int) → content string.  Errors per slide are caught; on failure
    the slide gets empty strings so the renderer can still copy the template.
    """
    results: List[Dict[int, str]] = []

    total = len(profiles)
    for profile in profiles:
        slide_num = profile.slide_idx + 1
        if not profile.slots:
            results.append({})
            continue

        try:
            content_map = _generate_for_slide(
                profile=profile,
                knowledge_filename=knowledge_filename,
                brand_id=brand_id,
                user_prompt=user_prompt,
                slide_num=slide_num,
                total_slides=total,
            )
        except Exception as exc:
            logger.error(
                f"[TemplateMergeContent] slide {slide_num} content generation failed: {exc}"
            )
            content_map = {slot.shape_id: "" for slot in profile.slots}

        results.append(content_map)

    return results


# ─── private ──────────────────────────────────────────────────────────────────

def _generate_for_slide(
    profile: SlideProfile,
    knowledge_filename: str,
    brand_id: int,
    user_prompt: str,
    slide_num: int,
    total_slides: int,
) -> Dict[int, str]:

    # Build RAG query: prefer the slide's own topic hint; fall back to user prompt
    rag_query = profile.hint or f"slide {slide_num} of {total_slides}: {user_prompt}"
    rag_context = ""
    try:
        rag_results = search_rag(
            query=rag_query,
            knowledge_source=knowledge_filename,
            k=_RAG_K,
            brand_id=brand_id,
        )
        if isinstance(rag_results, list):
            rag_context = "\n\n".join(str(r) for r in rag_results)
        else:
            rag_context = str(rag_results)
    except Exception as exc:
        logger.warning(f"[TemplateMergeContent] RAG failed for slide {slide_num}: {exc}")

    slots_desc = _describe_slots(profile.slots)
    prompt = _build_prompt(
        slide_num=slide_num,
        total_slides=total_slides,
        topic_hint=profile.hint or f"slide {slide_num}",
        user_prompt=user_prompt,
        rag_context=rag_context[:3000],
        slots_desc=slots_desc,
    )

    raw = generate_json(prompt)

    # raw is a dict keyed by string shape_id → text
    content_map: Dict[int, str] = {}
    for slot in profile.slots:
        key_str = str(slot.shape_id)
        value = raw.get(key_str, "")
        if isinstance(value, list):
            # bullets → join with newline for text frame injection
            value = "\n".join(str(v) for v in value[:6])
        content_map[slot.shape_id] = str(value)

    return content_map


def _describe_slots(slots: List[TextSlot]) -> str:
    lines = []
    for slot in slots:
        lines.append(
            f'  shape_id={slot.shape_id} role="{slot.role}" '
            f'char_limit={slot.char_limit} hint="{slot.hint[:60]}"'
        )
    return "\n".join(lines)


def _build_prompt(
    slide_num: int,
    total_slides: int,
    topic_hint: str,
    user_prompt: str,
    rag_context: str,
    slots_desc: str,
) -> str:
    return f"""You are a corporate presentation writer. Your task is to write content for slide {slide_num} of {total_slides}.

USER INTENT: {user_prompt}

SLIDE TOPIC HINT (from template): {topic_hint}

KNOWLEDGE CONTEXT (from document):
{rag_context}

SLIDE SLOTS TO FILL:
{slots_desc}

INSTRUCTIONS:
- Return a single JSON object with one key per shape_id (use the exact integer as a string key).
- For role="title": write a concise, impactful title (max char_limit characters).
- For role="body": write professional content. If the original hint suggests bullets, write a JSON array of strings (max 5 items). Otherwise write a paragraph.
- For role="footnote": write a short supporting fact or source note (max char_limit characters).
- Derive all content EXCLUSIVELY from the knowledge context. Do not invent data.
- Match the tone and vocabulary implied by the user intent.
- Respect char_limit strictly.

Respond with ONLY valid JSON, no markdown fences."""
