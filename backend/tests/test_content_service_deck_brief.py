"""
test_content_service_deck_brief.py — wiring del Deck Design Brief a Prompt
Architect, Outline Generator y Narrator (coherencia-artistica-pipeline.md,
tarea "Conectar el Deck Brief a Prompt Architect, Outline Generator y Narrator").

Verifica el prompt REALMENTE RENDERIZADO (no solo que la llamada no falla):
compara con y sin BrandArtisticEssence, usando prompts _v3/_v2 de prueba con
los placeholders nuevos.
"""
import pytest

import models
from services.generation.content_service import synthesize_presentation_outline
from utils.seed import CONFIGS

ARCHITECT_PROMPT_V3 = (
    "Topic: {topic} | Brand: {brand_name} | Tone: {tone_guideline} | Brief: {deck_brief}"
)
OUTLINE_PROMPT_V3 = (
    "Instruction: {polished_prompt} | RAG: {rag_context} | Lang: {target_lang} | "
    "Preferred: {preferred_grammar_types} | OpenClose: {opening_closing_hint}"
)


def _upsert_config(db_session, key, value):
    rec = db_session.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if rec:
        rec.value = value
    else:
        db_session.add(models.SystemConfig(key=key, value=value, description="test"))
    db_session.flush()


def _seed_v3_prompts(db_session):
    _upsert_config(db_session, "prompt_architect_v3", ARCHITECT_PROMPT_V3)
    _upsert_config(db_session, "prompt_content_outline_v3", OUTLINE_PROMPT_V3)


def _make_essence(db_session, brand_id):
    db_session.add(models.BrandArtisticEssence(
        brand_id=brand_id,
        source_filename="test_style.pptx",
        visual_strategy="Bold, editorial, high-contrast.",
        design_gestures={"visual_density": "dense"},
        slide_archetypes={"title": {"layout": "full-bleed"}},
    ))
    db_session.flush()


class _FakeGenerateJson:
    """Reemplaza providers.llm_provider.generate_json capturando cada prompt
    renderizado, para poder aserter sobre su contenido real."""

    def __init__(self):
        self.calls = []

    def __call__(self, prompt, specialization=None):
        self.calls.append(prompt)
        if "Brief:" in prompt:  # Prompt Architect
            return {"polished_instruction": "Do the thing"}
        if "Preferred:" in prompt:  # Outline Generator
            return {"slides": [{"title": "Slide 1", "section_label": "STRATEGY", "layout_type": "cover_hero"}]}
        return {}


def _run_outline(monkeypatch, db_session, job_id, fake_llm, narrator=None):
    import services.generation.content_service as content_service_module
    monkeypatch.setattr(content_service_module, "generate_json", fake_llm)
    # search_rag() llama a get_embedding() (proveedor real) — se reemplaza
    # por completo, no es parte de lo que este archivo prueba.
    monkeypatch.setattr(content_service_module, "search_rag", lambda *a, **k: "Fake RAG context.")
    return synthesize_presentation_outline(
        db_session, job_id,
        {
            "prompt": "AI trends",
            "style_filename": "test_style.pptx",
            "knowledge_filename": "knowledge.pptx",
            "region": "Global",
        },
    )


@pytest.mark.integration
class TestArchitectAndOutlinePromptsReceiveDeckBrief:

    def test_prompts_contain_deck_brief_values_when_essence_exists(self, monkeypatch, db_session, sample_brand, sample_job):
        _seed_v3_prompts(db_session)
        _make_essence(db_session, sample_brand.id)
        fake_llm = _FakeGenerateJson()

        manifest = _run_outline(monkeypatch, db_session, sample_job.id, fake_llm)

        architect_prompt = next(p for p in fake_llm.calls if "Brief:" in p)
        assert "Bold, editorial, high-contrast." in architect_prompt
        assert "dense" in architect_prompt

        outline_prompt = next(p for p in fake_llm.calls if "Preferred:" in p)
        assert "cover_hero" in outline_prompt  # "full-bleed" -> SLUG_ALIASES -> cover_hero

        assert manifest.deck_brief is not None
        assert manifest.deck_brief["visual_density"] == "dense"
        assert manifest.deck_brief["preferred_grammar_types"] == ["cover_hero"]

    def test_prompts_degrade_gracefully_without_essence(self, monkeypatch, db_session, sample_brand, sample_job):
        _seed_v3_prompts(db_session)
        # Sin BrandArtisticEssence — el pipeline no debe romperse.
        fake_llm = _FakeGenerateJson()

        manifest = _run_outline(monkeypatch, db_session, sample_job.id, fake_llm)

        architect_prompt = next(p for p in fake_llm.calls if "Brief:" in p)
        # El placeholder existe pero queda vacío — nunca "None" ni una excepción.
        assert "Brief: " in architect_prompt
        assert "None" not in architect_prompt.split("Brief:")[1]

        outline_prompt = next(p for p in fake_llm.calls if "Preferred:" in p)
        assert "No strong preference" in outline_prompt
        assert "No specific hint available." in outline_prompt

        assert manifest.deck_brief in (None, {})

    def test_falls_back_to_older_prompt_versions_when_v3_not_seeded(self, monkeypatch, db_session, sample_brand, sample_job):
        # v3 NO seedeado — el chain de fallback debe seguir funcionando
        # exactamente igual que antes de esta feature: prompt_architect_v1/
        # prompt_content_outline_v1 (sin {deck_brief}/{preferred_grammar_types})
        # no deben requerir esos placeholders para renderizar sin excepción.
        _upsert_config(db_session, "prompt_architect_v1", "Topic: {topic} | Brand: {brand_name} | Tone: {tone_guideline}")
        _upsert_config(db_session, "prompt_content_outline_v1", "Instruction: {polished_prompt} | RAG: {rag_context} | Lang: {target_lang}")

        # Por orden de llamada, no por contenido — v2 pudo quedar seedeado
        # ambientalmente por otro test/main.py en este mismo proceso de pytest,
        # y su texto real no es algo que este test deba conocer ni depender de él.
        responses = iter([
            {"polished_instruction": "Do the thing"},
            {"slides": [{"title": "Slide 1", "section_label": "STRATEGY", "layout_type": "strategic_split"}]},
        ])

        def fake_llm(prompt, specialization=None):
            return next(responses)

        manifest = _run_outline(monkeypatch, db_session, sample_job.id, fake_llm)
        assert len(manifest.slides) == 1


@pytest.mark.integration
class TestNarratorReceivesDeckBrief:

    def test_narrator_receives_visual_density_and_preferred_grammar_types(self, monkeypatch, db_session, sample_brand, sample_job):
        _seed_v3_prompts(db_session)
        _make_essence(db_session, sample_brand.id)
        fake_llm = _FakeGenerateJson()

        captured = {}

        class _FakeNarratorInstance:
            def __call__(self, **kwargs):
                captured.update(kwargs)
                return kwargs["slides_data"]

        def _fake_narrator_factory():
            return _FakeNarratorInstance()

        import services.generation.content_service as content_service_module
        monkeypatch.setattr(content_service_module, "generate_json", fake_llm)
        monkeypatch.setattr(content_service_module, "search_rag", lambda *a, **k: "Fake RAG context.")
        synthesize_presentation_outline(
            db_session, sample_job.id,
            {
                "prompt": "AI trends",
                "style_filename": "test_style.pptx",
                "knowledge_filename": "knowledge.pptx",
                "region": "Global",
            },
            narrator=_fake_narrator_factory,
        )

        assert captured.get("visual_density") == "dense"
        assert captured.get("preferred_grammar_types") == ["cover_hero"]


def _real_seeded_value(key: str) -> str:
    matches = [cfg["value"] for cfg in CONFIGS if cfg["key"] == key]
    assert len(matches) == 1
    return matches[0]


@pytest.mark.integration
class TestFullPipelineWithRealSeededPrompts:
    """
    Las clases de arriba usan plantillas mínimas de prueba para aislar qué
    valor recibe cada placeholder. Esta prueba corre el pipeline completo con
    el texto REAL sembrado en utils/seed.py (prompt_architect_v3,
    prompt_content_outline_v3) — cierra el hueco entre "el placeholder se
    formatea bien aislado" y "el prompt real de producción no explota".
    """

    def test_real_v3_prompts_survive_the_full_outline_pipeline(self, monkeypatch, db_session, sample_brand, sample_job):
        _upsert_config(db_session, "prompt_architect_v3", _real_seeded_value("prompt_architect_v3"))
        _upsert_config(db_session, "prompt_content_outline_v3", _real_seeded_value("prompt_content_outline_v3"))
        _make_essence(db_session, sample_brand.id)

        responses = iter([
            {"polished_instruction": "You are a Senior Strategic Lead. TONE: Bold, editorial."},
            {"slides": [
                {"title": "Cover", "section_label": "COVER", "layout_type": "composition_hero"},
                {"title": "Closing", "section_label": "NEXT STEPS", "layout_type": "composition_quote"},
            ]},
        ])

        def fake_llm(prompt, specialization=None):
            return next(responses)

        manifest = _run_outline(monkeypatch, db_session, sample_job.id, fake_llm)

        assert len(manifest.slides) == 2
        assert manifest.deck_brief["visual_density"] == "dense"
