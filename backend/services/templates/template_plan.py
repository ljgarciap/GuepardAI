"""
template_plan.py — Deck-level narrative planning for the Template Merge Engine (v2 Phase 2).

ONE LLM call per merge job, before any slide content is generated. Maps the
knowledge document onto the template's exact slide sequence and produces, per
slide: topic, key points and a retrieval query — plus the deck's target
language and tone. This is what gives the generated deck a narrative arc
instead of N independent slides, and what points RAG retrieval at the NEW
content instead of the old template's titles.

Degradation contract (ADR: docs/ai/contracts/default-llm-template-merge-outline-adr.md):
any failure — LLM error, malformed JSON, missing fields — returns None and
the pipeline falls back to v1 behavior. plan_deck() never raises.
Kill switch: system_configs.tm_outline_enabled (the call spends tokens).
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from providers.llm_provider import generate_json
from services.generation.content_service import search_rag
from services.templates.template_analyzer import SlideProfile
from services.templates.template_config import TemplateMergeConfig

logger = logging.getLogger(__name__)


@dataclass
class SlidePlan:
    topic: str
    key_points: List[str]
    rag_query: str


@dataclass
class DeckPlan:
    language: str
    tone: str
    slides: Dict[int, SlidePlan] = field(default_factory=dict)  # keyed by slide_idx (0-based)

    def for_slide(self, slide_idx: int) -> Optional[SlidePlan]:
        return self.slides.get(slide_idx)


def plan_deck(
    profiles: List[SlideProfile],
    knowledge_filename: str,
    brand_id: int,
    user_prompt: str,
    config: TemplateMergeConfig,
) -> Optional[DeckPlan]:
    """
    One generate_json() call (default routing) → DeckPlan, or None when the
    outline is disabled, the deck has no active slots, or anything fails.
    """
    if not config.outline_enabled:
        logger.info("[TemplatePlan] Outline disabled via tm_outline_enabled — skipping plan call.")
        return None

    active_profiles = [p for p in profiles if any(s.action != "preserve" for s in p.slots)]
    if not active_profiles:
        logger.info("[TemplatePlan] No slides with active slots — skipping plan call.")
        return None

    try:
        rag_context = ""
        try:
            rag_context = str(search_rag(
                query=user_prompt,
                knowledge_source=knowledge_filename,
                k=config.outline_rag_k,
                brand_id=brand_id,
            ))[:config.outline_context_max_chars]
        except Exception as exc:
            logger.warning(f"[TemplatePlan] Outline RAG failed (continuing without sample): {exc}")

        prompt = _build_prompt(profiles, user_prompt, rag_context)
        raw = generate_json(prompt)
        plan = _parse_plan(raw, profiles)
        if plan:
            logger.info(
                f"[TemplatePlan] Plan ready: language={plan.language} tone='{plan.tone}' "
                f"({len(plan.slides)}/{len(profiles)} slides planned)."
            )
        return plan
    except Exception as exc:
        logger.warning(f"[TemplatePlan] Plan call failed — degrading to v1 behavior: {exc}")
        return None


# ─── private ──────────────────────────────────────────────────────────────────

def _build_prompt(profiles: List[SlideProfile], user_prompt: str, rag_context: str) -> str:
    skeleton_lines = []
    for profile in profiles:
        slots_desc = ", ".join(
            f"{s.role}(limit {s.char_limit})" for s in profile.slots if s.action != "preserve"
        ) or "none editable"
        hints = " / ".join(s.hint[:60] for s in profile.slots if s.hint)[:160]
        skeleton_lines.append(
            f'  Slide {profile.slide_idx + 1}: slots=[{slots_desc}] existing_hints="{hints}"'
        )
    skeleton = "\n".join(skeleton_lines)
    total = len(profiles)

    return f"""You are the editorial planner for a corporate presentation. An existing PPTX template will be refilled with new content from a knowledge document. Plan the narrative BEFORE any slide is written.

USER INTENT: {user_prompt}

KNOWLEDGE DOCUMENT SAMPLE (representative excerpts):
{rag_context}

TEMPLATE STRUCTURE ({total} slides — the plan MUST keep exactly this slide count and order):
{skeleton}

TASK: Map the knowledge onto this exact slide sequence as ONE coherent narrative (opening, development, close). No two slides may repeat the same key point.

Return ONLY a valid JSON object, no markdown fences:
{{
  "language": "<ISO 639-1 code of the language the deck must be written in — follow the knowledge document / user intent>",
  "tone": "<3-6 words describing the writing tone>",
  "slides": [
    {{"slide": 1, "topic": "<one line>", "key_points": ["<point>", "<point>"], "rag_query": "<vector-search query, in the knowledge document's language, for the chunks this slide needs>"}}
  ]
}}
Rules:
1. Exactly one entry per slide, same order as the template.
2. key_points: 2-4 items, each a concrete fact to communicate, never invented.
3. rag_query must be specific to that slide's topic, not a copy of the topic of another slide."""


def _parse_plan(raw, profiles: List[SlideProfile]) -> Optional[DeckPlan]:
    """
    Tolerant per-entry parsing: an invalid entry is dropped (that slide
    degrades to v1); an invalid overall shape degrades the whole plan to None.
    Plan entries are 1-based in template order; they map onto profiles by
    position, landing on each profile's slide_idx.
    """
    if not isinstance(raw, dict):
        return None
    slides_raw = raw.get("slides")
    if not isinstance(slides_raw, list) or not slides_raw:
        return None

    language = raw.get("language")
    tone = raw.get("tone")
    plan = DeckPlan(
        language=language.strip().lower() if isinstance(language, str) and language.strip() else "",
        tone=tone.strip() if isinstance(tone, str) else "",
    )

    by_number = {}
    for entry in slides_raw:
        try:
            if not isinstance(entry, dict):
                continue
            number = int(entry.get("slide"))
            topic = entry.get("topic")
            rag_query = entry.get("rag_query")
            key_points = entry.get("key_points")
            if not (isinstance(topic, str) and topic.strip()):
                continue
            if not (isinstance(rag_query, str) and rag_query.strip()):
                continue
            if not isinstance(key_points, list):
                key_points = []
            key_points = [str(k).strip() for k in key_points if str(k).strip()][:6]
            by_number[number] = SlidePlan(
                topic=topic.strip(), key_points=key_points, rag_query=rag_query.strip(),
            )
        except Exception:
            continue

    for position, profile in enumerate(profiles, start=1):
        slide_plan = by_number.get(position)
        if slide_plan:
            plan.slides[profile.slide_idx] = slide_plan

    if not plan.slides:
        return None
    return plan
