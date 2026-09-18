"""
test_seed_prompts_deck_brief.py — Renderiza los 3 prompts reales sembrados en
utils/seed.py (prompt_architect_v3, prompt_content_outline_v3,
prompt_narrator_v2) con exactamente los kwargs que el código de producción
les pasa, para detectar un placeholder mal escrito (KeyError silencioso que
solo aparecería en producción, con la BD ya seedeada).

Spec: docs/specs/coherencia-artistica-pipeline.md, tarea "Seedear
prompt_architect_v3, prompt_content_outline_v3, prompt_narrator_v2".
"""
import pytest

from utils.seed import CONFIGS


def _get_config_value(key: str) -> str:
    matches = [cfg["value"] for cfg in CONFIGS if cfg["key"] == key]
    assert len(matches) == 1, f"esperaba exactamente 1 entrada para {key!r}, encontré {len(matches)}"
    return matches[0]


@pytest.mark.unit
class TestPromptArchitectV3Renders:

    def test_renders_with_deck_brief(self):
        prompt = _get_config_value("prompt_architect_v3").format(
            topic="AI trends in retail",
            brand_name="Acme Corp",
            tone_guideline="Professional executive tone.",
            deck_brief="Brand tone: Bold, editorial. | Visual density: dense",
        )
        assert "Bold, editorial." in prompt
        assert "Acme Corp" in prompt
        assert "AI trends in retail" in prompt

    def test_renders_with_empty_deck_brief(self):
        # Caso real cuando la marca no tiene BrandArtisticEssence.
        prompt = _get_config_value("prompt_architect_v3").format(
            topic="AI trends", brand_name="Acme Corp",
            tone_guideline="Professional executive tone.", deck_brief="",
        )
        assert "Professional executive tone." in prompt


@pytest.mark.unit
class TestPromptContentOutlineV3Renders:

    def test_renders_with_rhythm_signal(self):
        prompt = _get_config_value("prompt_content_outline_v3").format(
            polished_prompt="Mission: grow loyalty.",
            rag_context="Some RAG context.",
            target_lang="en",
            preferred_grammar_types="cover_hero, executive_quote",
            opening_closing_hint="Opening: cover_hero",
        )
        assert "cover_hero, executive_quote" in prompt
        assert "Opening: cover_hero" in prompt
        # El vocabulario "allowed" del prompt sigue siendo composition_* — el
        # rhythm signal no debe pretender ser una lista de layout_type válidos.
        assert "composition_hero" in prompt

    def test_renders_with_no_preference_fallback_text(self):
        prompt = _get_config_value("prompt_content_outline_v3").format(
            polished_prompt="Mission.", rag_context="Ctx.", target_lang="en",
            preferred_grammar_types="No strong preference — use your own judgment.",
            opening_closing_hint="No specific hint available.",
        )
        assert "No strong preference" in prompt


@pytest.mark.unit
class TestPromptNarratorV2Renders:

    def test_renders_with_visual_density_and_rhythm(self):
        prompt = _get_config_value("prompt_narrator_v2").format(
            slides_json="[]",
            brand_name="Acme Corp",
            target_lang="en",
            strategic_context="Global strategy.",
            slide_count=5,
            visual_density="dense",
            preferred_grammar_types="cover_hero",
        )
        assert "dense" in prompt
        assert "cover_hero" in prompt
        # Regla dura preexistente: el Narrator nunca puede tocar layout_type.
        assert 'NEVER change "title",\n   "layout_type"' in prompt or "NEVER change" in prompt
