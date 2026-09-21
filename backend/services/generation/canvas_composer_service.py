"""
canvas_composer_service.py — Artistic Generation Engine v2, Phase 1.
docs/specs/artistic-generation-v2.md

`compose_canvas_for_job()` is the v2_artistic replacement for
`art_director_service.plan_presentation_design()` — it reasons directly in
canvas_elements space (every slide is a custom_canvas decision from the
start) instead of picking a grammar_type label. Reuses the brand's mined
layout grammar (BrandLayoutGrammar, Phase 0) as few-shot exemplars.

Explicitly out of Phase 1's scope (v1's plan_presentation_design() does all
of this; v2 does none of it yet — not a regression, a deliberate first slice
per docs/specs/artistic-generation-v2.md's phasing):
  - Asset/image selection (find_best_assets) — every v2 slide today is
    text/shape/decorator only. The composer is explicitly told not to invent
    image sources (AI Architect ADR finding: no icon glyph library exists).
  - Premium enrichment pass (decoupled_art_director.PremiumArtDirector).
  - Layout-diversity history — v2 has no fixed grammar_type to repeat.

Never imports from or calls art_director_service.py / analyst_service.py's
LLM-calling functions — the isolation constraint (docs/specs/
artistic-generation-v2.md, "Non-negotiable constraint") means v1's Analyst/
Art Director code paths must stay completely unreached by v2_artistic jobs.
"""
import json
import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

import models
from providers import llm_provider

logger = logging.getLogger(__name__)

# Slides in these statuses are eligible for a (re)plan this call — CONTENT_READY
# is the first pass, PLANNED is a QA-triggered retry (only when flagged in qa_feedback).
_ELIGIBLE_STATUSES = (
    models.PresentationSlideStatus.CONTENT_READY,
    models.PresentationSlideStatus.PLANNED,
)


def compose_canvas_for_job(db: Session, job_id: int, qa_feedback: Optional[Dict[int, str]] = None) -> int:
    """Plans every eligible slide of `job_id` directly in canvas_elements space.
    Returns the number of slides processed. Raises if the brand has no mined
    layout grammar at all (docs/specs/artistic-generation-v2.md edge cases —
    a v2_artistic job must not silently fall back to v1 behavior)."""
    qa_feedback = qa_feedback or {}

    job = db.query(models.GenerationJob).get(job_id)
    if not job:
        raise ValueError(f"GenerationJob {job_id} not found")

    prompt_cfg = db.query(models.SystemConfig).filter(
        models.SystemConfig.key == "prompt_compose_canvas_v1"
    ).first()
    if not prompt_cfg:
        raise RuntimeError("prompt_compose_canvas_v1 is not seeded — run utils/seed.py")

    all_signatures = _load_brand_signatures(db, job.brand_id)

    slides = db.query(models.PresentationSlide).filter(
        models.PresentationSlide.job_id == job_id,
        models.PresentationSlide.status.in_(_ELIGIBLE_STATUSES),
    ).order_by(models.PresentationSlide.slide_number.asc()).all()

    processed = 0
    for slide in slides:
        if slide.status == models.PresentationSlideStatus.PLANNED and slide.slide_number not in qa_feedback:
            continue  # already planned by a previous v2 pass and not flagged for retry

        content_shape = _infer_content_shape(slide)
        exemplars = _select_exemplars(all_signatures, content_shape)
        feedback = qa_feedback.get(slide.slide_number)

        prompt = prompt_cfg.value.format(
            content_shape=content_shape,
            mined_signatures=json.dumps(exemplars, indent=2),
            slide_title=slide.title or "",
            slide_content=json.dumps(slide.content_json or {}),
            qa_feedback=feedback or "None — first attempt.",
        )

        raw = llm_provider.generate_premium_json(prompt)
        canvas_elements = raw.get("canvas_elements", []) if isinstance(raw, dict) else []
        design_reasoning = raw.get("design_reasoning", "") if isinstance(raw, dict) else ""
        if isinstance(design_reasoning, dict):
            design_reasoning = json.dumps(design_reasoning)

        planning = dict(slide.planning_json or {})
        planning["art_director"] = {
            "canvas_elements": canvas_elements,
            "reasoning": design_reasoning,
            "content_shape": content_shape,
            "engine_version": "v2_artistic",
        }
        slide.planning_json = planning
        slide.layout_slug = "custom_canvas"
        slide.status = models.PresentationSlideStatus.PLANNED

        db.add(models.ArtDirectorDecision(
            job_id=job_id, slide_number=slide.slide_number, decision_type="layout_selection",
            summary=f"ComposeCanvasTool (v2_artistic): {len(canvas_elements)} elements, content_shape={content_shape}",
            reasoning=design_reasoning,
            prompt_used=prompt, response_raw=json.dumps(raw, default=str),
            metadata_json={
                "engine_version": "v2_artistic",
                "content_shape": content_shape,
                "signature_names": [s.get("name") for s in exemplars],
            },
        ))
        processed += 1

    return processed


def _load_brand_signatures(db: Session, brand_id: int) -> List[dict]:
    rows = db.query(models.BrandLayoutGrammar).filter(
        models.BrandLayoutGrammar.brand_id == brand_id
    ).all()
    if not rows:
        raise ValueError(
            f"Brand {brand_id} has no mined layout grammar — run grammar mining "
            f"(Phase 0, MineLayoutGrammarTool) before generating with engine_version='v2_artistic'."
        )
    signatures: List[dict] = []
    for row in rows:
        signatures.extend(row.signatures_json or [])
    return signatures


def _infer_content_shape(slide: "models.PresentationSlide") -> str:
    """Deterministic, no LLM call: derived from content_json['layout_type'] (the
    Outline Generator's own vocabulary, already produced by the Redactor —
    composition_hero/composition_quote/etc., see CLAUDE.md's Outline Generator
    section) and the metrics list, not a dedicated 'content_shape' field — no
    such field exists anywhere in the pipeline today."""
    content = slide.content_json or {}
    layout_type = content.get("layout_type")
    if layout_type == "composition_quote":
        return "quote"
    if layout_type == "composition_hero" or slide.slide_number == 1:
        return "cover"
    if len(content.get("metrics") or []) >= 2:
        return "metric_comparison"
    return "narrative"


def _select_exemplars(signatures: List[dict], content_shape: str, limit: int = 3) -> List[dict]:
    matching = [s for s in signatures if s.get("content_shape") == content_shape]
    return (matching or signatures)[:limit]
