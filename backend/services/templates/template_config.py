"""
template_config.py — All tunable parameters for the Template Merge Engine.

Every value has a corresponding key in system_configs (seeded by utils/seed.py).
`TemplateMergeConfig.from_db()` reads them once at the start of the pipeline;
the loaded object is then passed to the analyzer, content generator, and renderer
so no downstream function ever calls the DB for configuration.

To change a value without redeploying: UPDATE system_configs SET value='...' WHERE key='...';
To override for a single run: set the corresponding ENV variable (uppercase key).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TemplateMergeConfig:
    # ── Shape filtering ──────────────────────────────────────────────────────
    # Non-placeholder shapes outside these area bounds are skipped entirely.
    shape_bg_area_threshold: float = 0.80    # > this fraction → background, skip
    shape_min_area_threshold: float = 0.005  # < this fraction → decorative dot, skip
    shape_min_text_length: int = 3           # existing text shorter than this → skip
    hint_max_chars: int = 200                # chars captured from existing text as hint

    # ── Char limits ───────────────────────────────────────────────────────────
    title_char_limit: int = 80
    footnote_char_limit: int = 120
    body_char_limit_min: int = 80
    body_char_limit_max: int = 600

    # Short-hint detection: hints shorter than this threshold indicate the slot
    # was designed for a key metric (e.g. "$45", "23%") and needs a tight limit.
    short_hint_threshold: int = 15
    short_hint_title_multiplier: int = 3   # char_limit = len(hint) * this (title)
    short_hint_body_multiplier: int = 4    # char_limit = len(hint) * this (body)

    # Body area-based estimate: chars_per_sq_inch × box_area_sq_in
    chars_per_sq_inch: int = 30

    # ── Role inference ────────────────────────────────────────────────────────
    footnote_area_fraction: float = 0.03  # shapes < this fraction of slide → footnote
    title_top_fraction: float = 0.20      # shapes in top fraction of slide height → title

    # ── Content generation ────────────────────────────────────────────────────
    rag_k: int = 6                    # RAG chunks retrieved per slide
    rag_context_max_chars: int = 3000  # max chars of RAG context passed to LLM
    max_bullet_items: int = 6          # max items when LLM returns a list for a body slot

    # ── Narrative plan (v2 Fase 2) ────────────────────────────────────────────
    # One deck-level LLM call before slide generation (spends tokens → kill
    # switch). Failure always degrades to v1 behavior, never aborts the job.
    outline_enabled: bool = True
    outline_rag_k: int = 8              # chunks sampled for the whole-doc outline
    outline_context_max_chars: int = 4000  # cap for the outline prompt's RAG sample

    # ── Slot action classification ─────────────────────────────────────────────
    # Non-placeholder shapes are classified into PRESERVE / ADAPT / REWRITE based
    # on the length of their existing hint text.  Placeholder shapes always REWRITE.
    preserve_max_hint_chars: int = 50   # hint ≤ this → PRESERVE (structural label)
    adapt_max_hint_chars: int = 150     # hint ≤ this → ADAPT (keep territory, replace data)
    # Comma-separated substrings; any match forces PRESERVE regardless of length.
    preserve_keywords: str = "confidential,proprietary,©,for reference only,preparado exclusivamente"

    # ── Traversal (v2) ────────────────────────────────────────────────────────
    # Maximum GroupShape nesting depth walked when collecting text frames;
    # groups beyond this depth are preserved as-is.
    group_max_depth: int = 3

    # ── Rendering ─────────────────────────────────────────────────────────────
    # What to do when the LLM returns "" for a rewrite slot:
    #   "blank" → clear the template's text (an empty box beats stale lorem)
    #   "keep"  → leave the original template text in place
    empty_rewrite_policy: str = "blank"

    @classmethod
    def from_db(cls) -> TemplateMergeConfig:
        """Load all tunables from system_configs (ENV overrides take priority)."""
        from providers.llm_provider import get_system_config

        def _f(key: str, default: str) -> float:
            return float(get_system_config(key, default))

        def _i(key: str, default: str) -> int:
            return int(get_system_config(key, default))

        return cls(
            shape_bg_area_threshold=_f("tm_shape_bg_area_threshold", "0.80"),
            shape_min_area_threshold=_f("tm_shape_min_area_threshold", "0.005"),
            shape_min_text_length=_i("tm_shape_min_text_length", "3"),
            hint_max_chars=_i("tm_hint_max_chars", "200"),
            title_char_limit=_i("tm_title_char_limit", "80"),
            footnote_char_limit=_i("tm_footnote_char_limit", "120"),
            body_char_limit_min=_i("tm_body_char_limit_min", "80"),
            body_char_limit_max=_i("tm_body_char_limit_max", "600"),
            short_hint_threshold=_i("tm_short_hint_threshold", "15"),
            short_hint_title_multiplier=_i("tm_short_hint_title_multiplier", "3"),
            short_hint_body_multiplier=_i("tm_short_hint_body_multiplier", "4"),
            chars_per_sq_inch=_i("tm_chars_per_sq_inch", "30"),
            footnote_area_fraction=_f("tm_footnote_area_fraction", "0.03"),
            title_top_fraction=_f("tm_title_top_fraction", "0.20"),
            rag_k=_i("tm_rag_k", "6"),
            rag_context_max_chars=_i("tm_rag_context_max_chars", "3000"),
            max_bullet_items=_i("tm_max_bullet_items", "6"),
            preserve_max_hint_chars=_i("tm_preserve_max_hint_chars", "50"),
            adapt_max_hint_chars=_i("tm_adapt_max_hint_chars", "150"),
            preserve_keywords=get_system_config(
                "tm_preserve_keywords",
                "confidential,proprietary,©,for reference only,preparado exclusivamente"
            ),
            group_max_depth=_i("tm_group_max_depth", "3"),
            empty_rewrite_policy=str(get_system_config("tm_empty_rewrite_policy", "blank")).strip().lower(),
            outline_enabled=str(get_system_config("tm_outline_enabled", "true")).strip().lower() == "true",
            outline_rag_k=_i("tm_outline_rag_k", "8"),
            outline_context_max_chars=_i("tm_outline_context_max_chars", "4000"),
        )
