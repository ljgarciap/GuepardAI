"""
deck_brief_service.py — Coherencia Artística del Pipeline (Deck Design Brief).

Destila BrandArtisticEssence + BrandPremiumVisualPattern en un JSON compacto,
construido UNA VEZ por job (no por slide), restringido a vocabulario que tiene
un ejecutor real en algún renderer del proyecto — nunca un atributo puramente
descriptivo que no llegue a ningún pixel. Ver docs/specs/coherencia-artistica-pipeline.md
(Auditoría de implementabilidad).

No es un BaseAgentTool: no hace ninguna llamada a LLM, es una lectura
determinista filtrada por whitelist — mismo criterio que search_rag()/
_build_manifest() en content_service.py (funciones de servicio planas).
Se llama con el `db: Session` que synthesize_presentation_outline ya tiene
abierto, antes del ThreadPoolExecutor del Step 4 — no cruza hilos.
"""
import json
from typing import Any, Dict, List

from sqlalchemy.orm import Session

import models
from services.ingestion.visual_pattern_service import (
    get_implemented_premium_patterns,
    get_latest_brand_patterns,
)

_VALID_DENSITIES = {"dense", "balanced", "minimal"}


def _get_field_max_chars(db: Session) -> int:
    cfg = db.query(models.SystemConfig).filter(
        models.SystemConfig.key == "deck_brief_field_max_chars"
    ).first()
    try:
        return int(cfg.value) if cfg else 400
    except (TypeError, ValueError):
        return 400


def _as_text(value: Any) -> str:
    """
    visual_strategy es una columna JSON pero en la práctica siempre se puebla
    con un string (artistic_essence_service.py mapea vision_result["visual_strategy"]
    directo). Si algún día llega un dict/list, se serializa en vez de romper.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _resolve_visual_density(design_gestures: Dict[str, Any], composition_rules: Dict[str, Any]) -> str:
    # El campo aparece en design_gestures según el prompt de ingestión actual
    # (artistic_essence_service.VISION_BRAND_EXTRACTION_PROMPT) y en
    # composition_rules según el comentario del modelo — se revisan ambos,
    # mismo criterio ya usado en visual_pattern_service.infer_patterns_from_essence().
    density = str(
        (design_gestures or {}).get("visual_density")
        or (composition_rules or {}).get("visual_density")
        or ""
    ).strip().lower()
    return density if density in _VALID_DENSITIES else "balanced"


def _collect_layout_candidates(essence: "models.BrandArtisticEssence") -> List[str]:
    """
    Reúne strings candidatos a grammar_type desde los dos únicos lugares de la
    esencia que realmente contienen algo parecido a un nombre de layout:
    preferred_layouts de los executable_visual_patterns, y las entradas de
    slide_archetypes (title/data/image/conclusion). No se inventan candidatos
    a partir de texto libre (visual_strategy, structural_archetypes) — eso
    sería exactamente el patrón "teórico, sin ejecutor real" que la spec prohíbe.
    """
    candidates: List[str] = []

    raw = essence.raw_vision_response or {}
    if isinstance(raw, dict):
        for pattern in raw.get("executable_visual_patterns") or []:
            if isinstance(pattern, dict):
                candidates.extend(
                    p for p in (pattern.get("preferred_layouts") or []) if isinstance(p, str)
                )

    slide_archetypes = essence.slide_archetypes or {}
    if isinstance(slide_archetypes, dict):
        for entry in slide_archetypes.values():
            if isinstance(entry, dict) and isinstance(entry.get("layout"), str):
                candidates.append(entry["layout"])
            elif isinstance(entry, str):
                candidates.append(entry)

    return candidates


def _to_recognized_grammar_types(candidates: List[str]) -> List[str]:
    """
    Filtra los candidatos contra GRAMMAR_GEOMETRIES.keys() (vía SLUG_ALIASES) —
    criterio explícito de la spec: un valor no reconocido se descarta
    individualmente, nunca invalida el brief completo. En la práctica esto
    devuelve vacío seguido mientras las esencias existentes usen vocabulario
    descriptivo (p. ej. "full-bleed-left") que no calza con ningún alias — es
    el comportamiento honesto hasta que se amplíe el vocabulario reconocido
    (ver Out of scope del spec), no un bug.
    """
    from services.ingestion.brand_composition_dna import GRAMMAR_GEOMETRIES, SLUG_ALIASES

    recognized: List[str] = []
    for raw_value in candidates:
        value = raw_value.strip()
        if not value:
            continue
        canonical = SLUG_ALIASES.get(value, value)
        if canonical not in GRAMMAR_GEOMETRIES:
            canonical = SLUG_ALIASES.get(value.replace("_", "-"), canonical)
        if canonical in GRAMMAR_GEOMETRIES and canonical not in recognized:
            recognized.append(canonical)
    return recognized


def _describe_archetype_entry(entry: Any) -> str:
    if isinstance(entry, dict):
        return str(entry.get("layout") or entry.get("treatment") or "")
    if isinstance(entry, str):
        return entry
    return ""


def _opening_closing_hint(slide_archetypes: Dict[str, Any], max_chars: int) -> str:
    if not isinstance(slide_archetypes, dict):
        return ""

    opening = _describe_archetype_entry(slide_archetypes.get("title"))
    closing = _describe_archetype_entry(slide_archetypes.get("conclusion"))

    parts = []
    if opening:
        parts.append(f"Opening: {opening}")
    if closing:
        parts.append(f"Closing: {closing}")
    return "; ".join(parts)[:max_chars]


def build_deck_brief(db: Session, brand_id: int) -> dict:
    """
    Destila la esencia artística de la marca en un brief compacto de deck:
    {
      "tone_note": str,
      "visual_density": "dense" | "balanced" | "minimal",
      "preferred_grammar_types": [str],       # subset de GRAMMAR_GEOMETRIES.keys()
      "renderable_premium_patterns": [str],   # subset de implemented_premium_patterns
      "opening_closing_hint": str,
    }

    Devuelve {} (nunca None, nunca excepción) si la marca no tiene
    BrandArtisticEssence — el pipeline sigue funcionando exactamente igual que
    hoy con los prompts de fallback (tone_guideline genérico).
    """
    if not brand_id:
        return {}

    essence = (
        db.query(models.BrandArtisticEssence)
        .filter(models.BrandArtisticEssence.brand_id == brand_id)
        .order_by(models.BrandArtisticEssence.updated_at.desc())
        .first()
    )
    if not essence:
        return {}

    max_chars = _get_field_max_chars(db)

    design_gestures = essence.design_gestures or {}
    composition_rules = essence.composition_rules or {}
    slide_archetypes = essence.slide_archetypes or {}

    preferred_grammar_types = _to_recognized_grammar_types(_collect_layout_candidates(essence))

    implemented_patterns = get_implemented_premium_patterns(db=db)
    stored_patterns = get_latest_brand_patterns(db, brand_id)
    renderable_premium_patterns = [
        p.get("pattern_type")
        for p in stored_patterns
        if isinstance(p, dict) and p.get("pattern_type") in implemented_patterns
    ]

    return {
        "tone_note": _as_text(essence.visual_strategy)[:max_chars],
        "visual_density": _resolve_visual_density(design_gestures, composition_rules),
        "preferred_grammar_types": preferred_grammar_types,
        "renderable_premium_patterns": renderable_premium_patterns,
        "opening_closing_hint": _opening_closing_hint(slide_archetypes, max_chars),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Formatters — cómo el brief se interpola en cada prompt consumidor.
# Centralizados aquí (no duplicados en content_service.py/narrator.py) para
# que Outline Generator y Narrator, que comparten preferred_grammar_types,
# lo rendericen exactamente igual.
# ─────────────────────────────────────────────────────────────────────────────

def format_grammar_type_list(values: Any) -> str:
    """Lista de grammar_type -> string legible para un prompt, o un mensaje
    explícito de 'sin preferencia' cuando viene vacía (nunca un placeholder
    vacío silencioso)."""
    clean = [v for v in (values or []) if isinstance(v, str) and v.strip()]
    return ", ".join(clean) if clean else "No strong preference — use your own judgment."


def summarize_for_architect_prompt(deck_brief: Dict[str, Any]) -> str:
    """Resumen de una línea del brief completo, para el placeholder
    {deck_brief} del Prompt Architect. Vacío si no hay brief — el prompt
    sigue funcionando con solo {tone_guideline} como hasta ahora."""
    if not deck_brief:
        return ""
    parts = []
    if deck_brief.get("tone_note"):
        parts.append(f"Brand tone: {deck_brief['tone_note']}")
    if deck_brief.get("visual_density"):
        parts.append(f"Visual density: {deck_brief['visual_density']}")
    if deck_brief.get("opening_closing_hint"):
        parts.append(f"Opening/closing pattern: {deck_brief['opening_closing_hint']}")
    return " | ".join(parts)
