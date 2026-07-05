"""
template_content.py — Generate text content for each slide of a template.

One LLM call per slide, returning a JSON dict keyed by shape_id → text string.
All tunables (RAG k, context window, bullet cap, etc.) come from TemplateMergeConfig.
"""
import logging
import re
from typing import Dict, List

from providers.llm_provider import generate_json
from services.generation.content_service import search_rag
from services.templates.template_analyzer import SlideProfile, TextSlot
from services.templates.template_config import TemplateMergeConfig

logger = logging.getLogger(__name__)


def generate_slide_contents(
    profiles: List[SlideProfile],
    knowledge_filename: str,
    brand_id: int,
    user_prompt: str,
    config: TemplateMergeConfig,
) -> List[Dict[int, str]]:
    """
    Returns a list parallel to `profiles`: each element maps shape_id → content string.
    Errors per slide are caught; the slide gets empty strings on failure.
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
                config=config,
            )
        except Exception as exc:
            logger.error(
                f"[TemplateMergeContent] slide {slide_num} failed: {exc}"
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
    config: TemplateMergeConfig,
) -> Dict[int, str]:

    # Split slots by action — PRESERVE slots never reach the LLM
    active_slots = [s for s in profile.slots if s.action != "preserve"]

    if not active_slots:
        logger.info(f"[TemplateMergeContent] slide {slide_num}: all slots preserved, skipping LLM call.")
        return {}

    rag_query = profile.hint or f"slide {slide_num} of {total_slides}: {user_prompt}"
    rag_context = ""
    try:
        rag_results = search_rag(
            query=rag_query,
            knowledge_source=knowledge_filename,
            k=config.rag_k,
            brand_id=brand_id,
        )
        rag_context = (
            "\n\n".join(str(r) for r in rag_results)
            if isinstance(rag_results, list)
            else str(rag_results)
        )
    except Exception as exc:
        logger.warning(f"[TemplateMergeContent] RAG failed for slide {slide_num}: {exc}")

    slots_desc = _describe_slots(active_slots)
    prompt = _build_prompt(
        slide_num=slide_num,
        total_slides=total_slides,
        topic_hint=profile.hint or f"slide {slide_num}",
        user_prompt=user_prompt,
        rag_context=rag_context[:config.rag_context_max_chars],
        slots_desc=slots_desc,
    )

    raw = generate_json(prompt)

    content_map: Dict[int, str] = {}
    for slot in active_slots:
        key_str = str(slot.shape_id)
        value = raw.get(key_str, "")

        # Unwrap nested LLM responses like {"content": "...", "role": "..."}
        value = _unwrap_value(value, config.max_bullet_items)

        # Strip any markdown that slipped through
        value = _strip_markdown(value)

        # Enforce char limit — prevents overflow in large-font or small boxes
        if value and len(value) > slot.char_limit:
            truncated = value[:slot.char_limit]
            last_space = truncated.rfind(' ')
            if last_space > slot.char_limit // 2:
                truncated = truncated[:last_space]
            value = truncated.rstrip('.,;: ') + '…'

        content_map[slot.shape_id] = value

    return content_map


def _unwrap_value(value, max_bullet_items: int) -> str:
    """Unwrap LLM responses that return nested objects instead of plain strings."""
    if isinstance(value, dict):
        for key in ('content', 'text', 'value', 'body', 'title'):
            if key in value and isinstance(value[key], str):
                return value[key]
        return ' '.join(str(v) for v in value.values() if v)
    if isinstance(value, list):
        return '\n'.join(str(v) for v in value[:max_bullet_items] if str(v).strip())

    # Handle LLM returning a Python-repr string: "{'role': ..., 'content': '...'}"
    # This happens when the LLM nests objects and generate_json returns them as
    # string values instead of actual dicts.
    text = str(value)
    if text.startswith("{") and ("'content'" in text or '"content"' in text):
        import ast
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, dict):
                for key in ('content', 'text', 'value', 'body', 'title'):
                    if key in parsed and isinstance(parsed[key], str):
                        return parsed[key]
        except Exception:
            pass

    return text


def _strip_markdown(text: str) -> str:
    """Remove markdown formatting so it does not appear as literal characters in PPTX."""
    if not text:
        return text
    text = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'_{1,2}(.+?)_{1,2}', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[\-\*\+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'^>\s+', '', text, flags=re.MULTILINE)
    return text.strip()


def _describe_slots(slots: List[TextSlot]) -> str:
    lines = []
    for s in slots:
        base = (
            f'  shape_id={s.shape_id} role="{s.role}" action="{s.action}" '
            f'char_limit={s.char_limit} hint="{s.hint[:60]}"'
        )
        if s.action == "adapt":
            base += "  ← ADAPT: keep same semantic territory and approximate length as hint"
        lines.append(base)
    return "\n".join(lines)


def _build_prompt(
    slide_num: int,
    total_slides: int,
    topic_hint: str,
    user_prompt: str,
    rag_context: str,
    slots_desc: str,
) -> str:
    return f"""You are a corporate presentation writer. Write content for slide {slide_num} of {total_slides}.

USER INTENT: {user_prompt}

SLIDE TOPIC HINT (from template): {topic_hint}

KNOWLEDGE CONTEXT (from document):
{rag_context}

SLIDE SLOTS TO FILL:
{slots_desc}

STRICT FORMAT RULES — follow exactly or the output will be broken:
1. Return ONLY a flat JSON object: {{"shape_id_string": "text content", ...}}
2. All values MUST be plain strings — NEVER nest objects, NEVER return {{"role": ..., "content": ...}}
3. NO markdown — no **, no *, no #, no -, no backticks, no underscores for formatting
4. Respect char_limit strictly — count every character including spaces
5. For role="title": concise impactful title, max char_limit characters
6. For role="body": professional prose or bullet items separated by newlines, max char_limit total
7. For role="footnote": short supporting fact or source note, max char_limit characters
8. Derive all content EXCLUSIVELY from the knowledge context; do not invent data
9. If no relevant data exists for a slot, return an empty string ""
10. Use only shape_ids listed in SLIDE SLOTS; do not add extra keys
11. For action="adapt" slots: rewrite the hint with data from the knowledge context but keep
    the same semantic territory (same type of information) and stay within char_limit

Respond with ONLY valid JSON — no markdown fences, no extra text."""
