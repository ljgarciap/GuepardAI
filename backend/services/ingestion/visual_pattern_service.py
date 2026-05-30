"""
Isolated pattern service for Premium Visual Agent experiments.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

import models
from sqlalchemy.orm import Session


SUPPORTED_PATTERN_TYPES = {
    "object_as_letter",
    "typographic_substitution",
    "editorial_split",
    "brand_footer",
    "logo_locked_footer",
    "full_bleed_hero",
    "image_masked_title",
    "data_cards_brand_grid",
}


DEFAULT_PATTERN_WEIGHTS = {
    "object_as_letter": 0.82,
    "typographic_substitution": 0.78,
    "editorial_split": 0.86,
    "brand_footer": 0.7,
    "logo_locked_footer": 0.74,
    "full_bleed_hero": 0.84,
    "image_masked_title": 0.8,
    "data_cards_brand_grid": 0.76,
}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value:
        return [value]
    return []


def _normalize_pattern(raw_pattern: Any, index: int) -> Optional[Dict[str, Any]]:
    if isinstance(raw_pattern, str):
        pattern_type = raw_pattern.strip().lower()
        raw_data: Dict[str, Any] = {"description": raw_pattern}
    elif isinstance(raw_pattern, dict):
        raw_data = raw_pattern
        pattern_type = str(
            raw_data.get("pattern_type")
            or raw_data.get("type")
            or raw_data.get("name")
            or ""
        ).strip().lower()
    else:
        return None

    if pattern_type not in SUPPORTED_PATTERN_TYPES:
        return None

    return {
        "id": raw_data.get("id") or f"{pattern_type}_{index + 1}",
        "pattern_type": pattern_type,
        "description": raw_data.get("description") or raw_data.get("rationale") or "",
        "execution_hint": raw_data.get("execution_hint") or raw_data.get("css_hint") or "",
        "preferred_layouts": _as_list(raw_data.get("preferred_layouts") or raw_data.get("layouts")),
        "asset_role": raw_data.get("asset_role") or "supporting",
        "confidence": float(raw_data.get("confidence") or DEFAULT_PATTERN_WEIGHTS.get(pattern_type, 0.65)),
        "source_slide": raw_data.get("source_slide"),
        "constraints": raw_data.get("constraints") or {},
    }


def infer_patterns_from_essence(essence: Dict[str, Any]) -> List[Dict[str, Any]]:
    gestures = essence.get("design_gestures") or {}
    composition = essence.get("composition_rules") or {}
    structural = essence.get("structural_archetypes") or {}
    visual_strategy = str(essence.get("visual_strategy") or "")

    inferred: List[Dict[str, Any]] = []

    persistent_blocks = structural.get("persistent_blocks") or []
    if persistent_blocks or composition.get("logo_position"):
        inferred.append({
            "pattern_type": "logo_locked_footer",
            "description": "Persistent logo/metadata lockup appears across slides.",
            "preferred_layouts": ["composition_split", "composition_hero", "data_grid_cards"],
            "confidence": 0.72,
            "constraints": {"logo_position": composition.get("logo_position", "bottom-right")},
        })

    image_role = str(composition.get("image_role") or "").lower()
    if "hero" in image_role or "full" in visual_strategy.lower():
        inferred.append({
            "pattern_type": "full_bleed_hero",
            "description": "Large image-led compositions with text overlay or adjacent editorial block.",
            "preferred_layouts": ["composition_hero", "hero"],
            "confidence": 0.76,
        })

    density = str(gestures.get("visual_density") or composition.get("visual_density") or "").lower()
    if "dense" in density or "grid" in visual_strategy.lower():
        inferred.append({
            "pattern_type": "data_cards_brand_grid",
            "description": "Structured KPI grid with branded cards and strong hierarchy.",
            "preferred_layouts": ["data_grid_cards", "data_grid"],
            "confidence": 0.7,
        })

    typography = str(composition.get("typography_style") or "").lower()
    if any(token in typography for token in ["mask", "image", "substitution", "editorial"]):
        inferred.append({
            "pattern_type": "image_masked_title",
            "description": "Display typography can accept image or object treatments.",
            "preferred_layouts": ["composition_hero", "composition_split"],
            "confidence": 0.68,
        })

    if not inferred:
        inferred.extend([
            {
                "pattern_type": "editorial_split",
                "description": "Default premium editorial split with disciplined image/text rhythm.",
                "preferred_layouts": ["composition_split", "composition_pillars"],
                "confidence": 1.0,
            },
            {
                "pattern_type": "full_bleed_hero",
                "description": "Large image-led compositions with text overlay. Great for covers and section breaks.",
                "preferred_layouts": ["composition_hero", "hero"],
                "confidence": 1.0,
            },
            {
                "pattern_type": "data_cards_brand_grid",
                "description": "Structured KPI grid with branded cards. Perfect for metrics and multiple data points.",
                "preferred_layouts": ["data_grid_cards", "data_grid"],
                "confidence": 1.0,
            }
        ])

    return [
        normalized
        for i, pattern in enumerate(inferred)
        if (normalized := _normalize_pattern(pattern, i))
    ]


def normalize_executable_patterns(vision_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    direct_patterns = (
        vision_result.get("executable_visual_patterns")
        or vision_result.get("visual_patterns")
        or vision_result.get("patterns")
        or []
    )

    normalized = [
        pattern
        for i, raw_pattern in enumerate(_as_list(direct_patterns))
        if (pattern := _normalize_pattern(raw_pattern, i))
    ]

    if normalized:
        return normalized

    return infer_patterns_from_essence(vision_result)


def summarize_patterns(patterns: Iterable[Dict[str, Any]]) -> str:
    return "; ".join(
        f"{p.get('pattern_type')} ({p.get('confidence', 0):.2f})"
        for p in patterns
    )


def upsert_brand_patterns(
    db: Session,
    brand_id: Optional[int],
    source_filename: str,
    patterns: List[Dict[str, Any]],
    raw_extraction: Optional[Dict[str, Any]] = None,
) -> Optional[models.BrandPremiumVisualPattern]:
    if not brand_id:
        return None

    record = (
        db.query(models.BrandPremiumVisualPattern)
        .filter(models.BrandPremiumVisualPattern.brand_id == brand_id)
        .first()
    )
    if not record:
        record = models.BrandPremiumVisualPattern(
            brand_id=brand_id,
            source_filename=source_filename,
        )
        db.add(record)

    record.source_filename = source_filename
    record.patterns_json = patterns
    record.pattern_summary = summarize_patterns(patterns)
    record.raw_extraction = raw_extraction or {}
    return record


def get_latest_brand_patterns(db: Session, brand_id: Optional[int]) -> List[Dict[str, Any]]:
    if not brand_id:
        return []

    record = (
        db.query(models.BrandPremiumVisualPattern)
        .filter(models.BrandPremiumVisualPattern.brand_id == brand_id)
        .order_by(models.BrandPremiumVisualPattern.updated_at.desc())
        .first()
    )
    return record.patterns_json if record and record.patterns_json else []
