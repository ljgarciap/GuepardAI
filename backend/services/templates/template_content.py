"""
template_content.py — Generate text content for each slide of a template.

One LLM call per slide, returning a JSON dict keyed by slot_key → text string.
All tunables (RAG k, context window, bullet cap, etc.) come from TemplateMergeConfig.

v2 Phase 2 (ADR: default-llm-template-merge-content-adr-v2.md): when a DeckPlan
is available, each slide's prompt carries the plan's topic/key points/tone, a
one-line summary of every previously generated slide (anti-repetition), and a
pinned output language; the RAG query comes from the plan instead of the old
template's hints, and chunks already used verbatim by previous slides are
de-prioritized in the context.
"""
import logging
import re
from typing import Dict, List, Optional, Set

from providers.llm_provider import generate_json
from services.generation.content_service import search_rag
from services.templates.template_analyzer import SlideProfile, TextSlot
from services.templates.template_config import TemplateMergeConfig
from services.templates.template_plan import DeckPlan, SlidePlan

logger = logging.getLogger(__name__)

_CHUNK_SEPARATOR = "\n---\n"   # how search_rag joins chunks
_PREV_SUMMARY_MAX_CHARS = 100


def generate_slide_contents(
    profiles: List[SlideProfile],
    knowledge_filename: str,
    brand_id: int,
    user_prompt: str,
    config: TemplateMergeConfig,
    plan: Optional[DeckPlan] = None,
) -> List[Optional[Dict[str, str]]]:
    """
    Returns a list parallel to `profiles`: each element maps slot_key → content
    string. A slide whose generation failed entirely (LLM exception) yields
    None instead of a dict — the renderer keeps that slide's original text and
    reports its slots as `failed`, rather than blanking them.

    `plan` is the deck-level narrative plan (or None → v1 behavior).
    """
    results: List[Optional[Dict[str, str]]] = []
    total = len(profiles)
    prev_summaries: List[str] = []
    used_chunks: Set[str] = set()

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
                plan_slide=plan.for_slide(profile.slide_idx) if plan else None,
                language=plan.language if plan else "",
                tone=plan.tone if plan else "",
                prev_summaries=prev_summaries,
                used_chunks=used_chunks,
            )
            summary = _summarize_slide(profile, content_map)
            if summary:
                prev_summaries.append(f"Slide {slide_num}: {summary}")
        except Exception as exc:
            logger.error(
                f"[TemplateMergeContent] slide {slide_num} failed: {exc}"
            )
            content_map = None

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
    plan_slide: Optional[SlidePlan] = None,
    language: str = "",
    tone: str = "",
    prev_summaries: Optional[List[str]] = None,
    used_chunks: Optional[Set[str]] = None,
) -> Dict[str, str]:

    # Split slots by action — PRESERVE slots never reach the LLM
    active_slots = [s for s in profile.slots if s.action != "preserve"]

    if not active_slots:
        logger.info(f"[TemplateMergeContent] slide {slide_num}: all slots preserved, skipping LLM call.")
        return {}

    # RAG query: the plan's per-slide query targets the NEW content; the v1
    # fallback (old template hints) only applies when there is no plan.
    if plan_slide:
        rag_query = plan_slide.rag_query
    else:
        rag_query = profile.hint or f"slide {slide_num} of {total_slides}: {user_prompt}"

    rag_context = ""
    try:
        rag_results = search_rag(
            query=rag_query,
            knowledge_source=knowledge_filename,
            k=config.rag_k,
            brand_id=brand_id,
        )
        raw_context = (
            "\n\n".join(str(r) for r in rag_results)
            if isinstance(rag_results, list)
            else str(rag_results)
        )
        rag_context = _deprioritize_used_chunks(
            raw_context, used_chunks, config.rag_context_max_chars
        )
    except Exception as exc:
        logger.warning(f"[TemplateMergeContent] RAG failed for slide {slide_num}: {exc}")

    slots_desc = _describe_slots(active_slots)
    prompt = _build_prompt(
        slide_num=slide_num,
        total_slides=total_slides,
        topic_hint=profile.hint or f"slide {slide_num}",
        user_prompt=user_prompt,
        rag_context=rag_context,
        slots_desc=slots_desc,
        plan_slide=plan_slide,
        language=language,
        tone=tone,
        prev_summaries=prev_summaries or [],
    )

    raw = generate_json(prompt)

    content_map: Dict[str, str] = {}
    for slot in active_slots:
        # Unwrap nested LLM responses + strip markdown that slipped through
        value = _unwrap_value(raw.get(slot.slot_key, ""), config.max_bullet_items)
        content_map[slot.slot_key] = _strip_markdown(value)

    # Fit-check (v2 Fase 3): overflowing slots get batched shorten-retry
    # call(s) before any truncation — a rewritten-short text always beats a cut.
    for _ in range(max(0, config.fitcheck_max_retries)):
        overflowing = [
            s for s in active_slots
            if len(content_map.get(s.slot_key) or "") > s.char_limit
        ]
        if not overflowing:
            break
        content_map = _shorten_overflowing(
            content_map, overflowing, config, slide_num, language
        )

    # Last resort: truncate — sentence boundary first, word boundary + ellipsis after
    for slot in active_slots:
        value = content_map.get(slot.slot_key) or ""
        if value and len(value) > slot.char_limit:
            content_map[slot.slot_key] = _truncate_to_limit(value, slot.char_limit)

    return content_map


def _shorten_overflowing(
    content_map: Dict[str, str],
    slots: List[TextSlot],
    config: TemplateMergeConfig,
    slide_num: int,
    language: str,
) -> Dict[str, str]:
    """One batched LLM call asking to rewrite overflowing texts within budget.
    Any failure leaves the original values in place (truncation handles them)."""
    lines = []
    for s in slots:
        current = content_map.get(s.slot_key) or ""
        lines.append(
            f'  slot_id="{s.slot_key}" char_limit={s.char_limit} current_text="{current}"'
        )
    lang_rule = (
        f'Keep the language: "{language}".' if language
        else "Keep each text's original language."
    )
    prompt = f"""You are editing a corporate presentation (slide {slide_num}). The following texts EXCEED their character limits. Rewrite each one to fit STRICTLY within its char_limit while keeping its key point. {lang_rule}

TEXTS TO SHORTEN:
{chr(10).join(lines)}

RULES:
1. Return ONLY a flat JSON object: {{"slot_id": "shortened text", ...}} — keys exactly as listed
2. Every value MUST be at most its char_limit characters — count every character including spaces
3. Preserve the most important fact of each text; drop secondary detail
4. NO markdown; plain strings only; keep newlines if the original had them

Respond with ONLY valid JSON — no markdown fences, no extra text."""

    try:
        raw = generate_json(prompt)
    except Exception as exc:
        logger.warning(f"[TemplateMergeContent] slide {slide_num}: shorten-retry failed: {exc}")
        return content_map

    for s in slots:
        value = _strip_markdown(_unwrap_value(raw.get(s.slot_key, ""), config.max_bullet_items)).strip()
        original = content_map.get(s.slot_key) or ""
        if value and len(value) < len(original):
            content_map[s.slot_key] = value
    return content_map


def _truncate_to_limit(value: str, limit: int) -> str:
    """Sentence-boundary truncation; word boundary + ellipsis as last resort."""
    truncated = value[:limit]
    best = -1
    for punct in ('. ', '! ', '? ', '.\n', '!\n', '?\n'):
        best = max(best, truncated.rfind(punct))
    if truncated and truncated[-1] in '.!?':
        best = max(best, len(truncated) - 1)
    if best > limit // 2:
        return truncated[:best + 1].rstrip()
    last_space = truncated.rfind(' ')
    if last_space > limit // 2:
        truncated = truncated[:last_space]
    return truncated.rstrip('.,;: ') + '…'


def _deprioritize_used_chunks(
    raw_context: str, used_chunks: Optional[Set[str]], max_chars: int
) -> str:
    """
    Reorder RAG chunks so the ones already used verbatim by previous slides go
    LAST (the char cap drops them first). Chunks that survive into the final
    context are registered in `used_chunks` for the following slides.
    """
    if not raw_context:
        return raw_context
    if used_chunks is None:
        used_chunks = set()

    chunks = [c.strip() for c in raw_context.split(_CHUNK_SEPARATOR) if c.strip()]
    if not chunks:
        return raw_context[:max_chars]

    fresh = [c for c in chunks if c not in used_chunks]
    stale = [c for c in chunks if c in used_chunks]

    final_chunks: List[str] = []
    budget = max_chars
    for chunk in fresh + stale:
        cost = len(chunk) + (len(_CHUNK_SEPARATOR) if final_chunks else 0)
        if cost > budget:
            break
        final_chunks.append(chunk)
        budget -= cost

    if not final_chunks and chunks:
        # A single oversized chunk: keep its head rather than sending nothing
        final_chunks = [chunks[0][:max_chars]]

    for chunk in final_chunks:
        used_chunks.add(chunk)
    return _CHUNK_SEPARATOR.join(final_chunks)


def _summarize_slide(profile: SlideProfile, content_map: Optional[Dict[str, str]]) -> str:
    """One-line summary of what a slide ended up saying (for anti-repetition)."""
    if not content_map:
        return ""
    by_key = {s.slot_key: s for s in profile.slots}
    # Prefer the generated title; fall back to the first non-empty value
    candidates = sorted(
        ((k, v) for k, v in content_map.items() if v and v.strip()),
        key=lambda kv: 0 if getattr(by_key.get(kv[0]), "role", "") == "title" else 1,
    )
    if not candidates:
        return ""
    text = candidates[0][1].strip().replace("\n", " · ")
    return text[:_PREV_SUMMARY_MAX_CHARS]


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
            f'  slot_id="{s.slot_key}" role="{s.role}" action="{s.action}" '
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
    plan_slide: Optional[SlidePlan] = None,
    language: str = "",
    tone: str = "",
    prev_summaries: Optional[List[str]] = None,
) -> str:
    plan_section = ""
    if plan_slide:
        points = "\n".join(f"  - {p}" for p in plan_slide.key_points) or "  (planner gave no key points)"
        tone_line = f"Deck tone: {tone}\n" if tone else ""
        plan_section = f"""
DECK PLAN (follow it — this slide's assignment in the deck's narrative):
{tone_line}This slide's topic: {plan_slide.topic}
Key points to communicate:
{points}
"""

    prev_section = ""
    if prev_summaries:
        lines = "\n".join(f"  {s}" for s in prev_summaries)
        prev_section = f"""
PREVIOUS SLIDES (already written — do NOT repeat their points):
{lines}
"""

    if language:
        language_rule = f'12. LANGUAGE: write ALL content in "{language}" — every slot, no exceptions'
    else:
        language_rule = "12. LANGUAGE: write ALL content in the same language as the USER INTENT"

    return f"""You are a corporate presentation writer. Write content for slide {slide_num} of {total_slides}.

USER INTENT: {user_prompt}

SLIDE TOPIC HINT (from template): {topic_hint}
{plan_section}{prev_section}
KNOWLEDGE CONTEXT (from document):
{rag_context}

SLIDE SLOTS TO FILL:
{slots_desc}

STRICT FORMAT RULES — follow exactly or the output will be broken:
1. Return ONLY a flat JSON object: {{"slot_id": "text content", ...}} — keys are the slot_id strings EXACTLY as listed above
2. All values MUST be plain strings — NEVER nest objects, NEVER return {{"role": ..., "content": ...}}
3. NO markdown — no **, no *, no #, no -, no backticks, no underscores for formatting
4. Respect char_limit strictly — count every character including spaces
5. For role="title": concise impactful title, max char_limit characters
6. For role="body": professional prose or bullet items separated by newlines, max char_limit total
7. For role="footnote": short supporting fact or source note, max char_limit characters
8. Derive all content EXCLUSIVELY from the knowledge context; do not invent data
9. If no relevant data exists for a slot, return an empty string ""
10. Use only slot_ids listed in SLIDE SLOTS; do not add extra keys
11. For action="adapt" slots: rewrite the hint with data from the knowledge context but keep
    the same semantic territory (same type of information) and stay within char_limit
{language_rule}

Respond with ONLY valid JSON — no markdown fences, no extra text."""
