"""
test_deck_brief_service.py — Deck Design Brief (Coherencia Artística del Pipeline).

Cubre docs/specs/coherencia-artistica-pipeline.md, tarea "Implementar
deck_brief_service.build_deck_brief()": shape del brief, fallback a {} sin
esencia, resolución de visual_density desde las dos fuentes posibles,
reconocimiento estricto de grammar_type contra GRAMMAR_GEOMETRIES,
intersección con la whitelist de pattern_type implementados, y truncado
configurable de campos de texto.
"""
import json

import pytest

import models
from services.generation.deck_brief_service import build_deck_brief


def _upsert_config(db_session, key, value):
    rec = db_session.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if rec:
        rec.value = value
    else:
        db_session.add(models.SystemConfig(key=key, value=value, description="test"))
    db_session.flush()


def _make_essence(db_session, brand_id, **overrides):
    essence = models.BrandArtisticEssence(
        brand_id=brand_id,
        source_filename="test_style.pptx",
        visual_strategy=overrides.get("visual_strategy"),
        slide_archetypes=overrides.get("slide_archetypes"),
        structural_archetypes=overrides.get("structural_archetypes"),
        design_gestures=overrides.get("design_gestures"),
        composition_rules=overrides.get("composition_rules"),
        art_direction_note=overrides.get("art_direction_note"),
        raw_vision_response=overrides.get("raw_vision_response"),
    )
    db_session.add(essence)
    db_session.flush()
    return essence


@pytest.mark.integration
class TestBuildDeckBriefFallback:

    def test_returns_empty_dict_when_no_essence(self, db_session, sample_brand):
        assert build_deck_brief(db_session, sample_brand.id) == {}

    def test_returns_empty_dict_when_brand_id_falsy(self, db_session):
        assert build_deck_brief(db_session, None) == {}
        assert build_deck_brief(db_session, 0) == {}

    def test_defaults_when_essence_is_completely_sparse(self, db_session, sample_brand):
        _make_essence(db_session, sample_brand.id)
        brief = build_deck_brief(db_session, sample_brand.id)

        assert brief["tone_note"] == ""
        assert brief["visual_density"] == "balanced"
        assert brief["preferred_grammar_types"] == []
        assert brief["renderable_premium_patterns"] == []
        assert brief["opening_closing_hint"] == ""


@pytest.mark.integration
class TestVisualDensityResolution:

    def test_from_design_gestures(self, db_session, sample_brand):
        _make_essence(db_session, sample_brand.id, design_gestures={"visual_density": "dense"})
        brief = build_deck_brief(db_session, sample_brand.id)
        assert brief["visual_density"] == "dense"

    def test_from_composition_rules_when_design_gestures_missing(self, db_session, sample_brand):
        _make_essence(db_session, sample_brand.id, composition_rules={"visual_density": "minimal"})
        brief = build_deck_brief(db_session, sample_brand.id)
        assert brief["visual_density"] == "minimal"

    def test_design_gestures_takes_priority_over_composition_rules(self, db_session, sample_brand):
        _make_essence(
            db_session, sample_brand.id,
            design_gestures={"visual_density": "dense"},
            composition_rules={"visual_density": "minimal"},
        )
        brief = build_deck_brief(db_session, sample_brand.id)
        assert brief["visual_density"] == "dense"

    def test_invalid_value_falls_back_to_balanced(self, db_session, sample_brand):
        _make_essence(db_session, sample_brand.id, design_gestures={"visual_density": "chaotic"})
        brief = build_deck_brief(db_session, sample_brand.id)
        assert brief["visual_density"] == "balanced"


@pytest.mark.integration
class TestPreferredGrammarTypes:

    def test_recognizes_slug_alias_from_preferred_layouts(self, db_session, sample_brand):
        _make_essence(
            db_session, sample_brand.id,
            raw_vision_response={
                "executable_visual_patterns": [
                    {"pattern_type": "full_bleed_hero", "preferred_layouts": ["full-bleed", "unknown_thing"]},
                ]
            },
        )
        brief = build_deck_brief(db_session, sample_brand.id)
        assert brief["preferred_grammar_types"] == ["cover_hero"]

    def test_recognizes_layout_from_slide_archetypes(self, db_session, sample_brand):
        _make_essence(
            db_session, sample_brand.id,
            slide_archetypes={"title": {"layout": "quote-hero"}},
        )
        brief = build_deck_brief(db_session, sample_brand.id)
        assert brief["preferred_grammar_types"] == ["executive_quote"]

    def test_unrecognized_candidate_is_discarded_individually(self, db_session, sample_brand):
        _make_essence(
            db_session, sample_brand.id,
            slide_archetypes={
                "title": {"layout": "full-bleed-left"},  # no calza con ningún alias -> descartado
                "data": {"layout": "data-cards"},        # SLUG_ALIASES -> data_grid_cards (sí calza)
            },
        )
        brief = build_deck_brief(db_session, sample_brand.id)
        assert brief["preferred_grammar_types"] == ["data_grid_cards"]

    def test_deduplicates_candidates_resolving_to_the_same_canonical(self, db_session, sample_brand):
        _make_essence(
            db_session, sample_brand.id,
            slide_archetypes={
                "title": {"layout": "dark-hero"},   # -> cover_hero
                "image": {"layout": "full-bleed"},  # -> cover_hero también
            },
        )
        brief = build_deck_brief(db_session, sample_brand.id)
        assert brief["preferred_grammar_types"] == ["cover_hero"]

    def test_bare_data_grid_alias_is_not_recognized_here_unlike_data_grid_cards(self, db_session, sample_brand):
        # "data-grid" (SLUG_ALIASES) resuelve al canónico "data_grid" (sin
        # "_cards"), que NO es una key de GRAMMAR_GEOMETRIES (solo
        # "data_grid_cards" lo es) — mismo hallazgo que motivó agregar una
        # entrada explícita en GRAMMAR_TO_ARTISTIC_PDF para el path PDF legacy.
        # Aquí el criterio de la spec es estricto ("solo claves presentes en
        # GRAMMAR_GEOMETRIES"), así que se descarta — comportamiento esperado,
        # no un bug de este archivo.
        _make_essence(db_session, sample_brand.id, slide_archetypes={"data": {"layout": "data-grid"}})
        brief = build_deck_brief(db_session, sample_brand.id)
        assert brief["preferred_grammar_types"] == []

    def test_no_recognizable_candidates_yields_empty_list_not_exception(self, db_session, sample_brand):
        _make_essence(
            db_session, sample_brand.id,
            structural_archetypes={"persistent_blocks": [{"type": "accent_line"}]},
            slide_archetypes={"title": "some free-form descriptive text"},
        )
        brief = build_deck_brief(db_session, sample_brand.id)
        assert brief["preferred_grammar_types"] == []


@pytest.mark.integration
class TestRenderablePremiumPatterns:

    def test_intersects_with_implemented_whitelist(self, db_session, sample_brand):
        _upsert_config(
            db_session, "implemented_premium_patterns",
            json.dumps(["full_bleed_hero", "data_cards_brand_grid", "editorial_split"]),
        )
        db_session.add(models.BrandPremiumVisualPattern(
            brand_id=sample_brand.id,
            source_filename="test_style.pptx",
            patterns_json=[
                {"pattern_type": "full_bleed_hero", "confidence": 0.9},
                {"pattern_type": "object_as_letter", "confidence": 0.8},
            ],
        ))
        db_session.flush()
        _make_essence(db_session, sample_brand.id)

        brief = build_deck_brief(db_session, sample_brand.id)
        assert brief["renderable_premium_patterns"] == ["full_bleed_hero"]

    def test_no_stored_patterns_yields_empty_list(self, db_session, sample_brand):
        _make_essence(db_session, sample_brand.id)
        brief = build_deck_brief(db_session, sample_brand.id)
        assert brief["renderable_premium_patterns"] == []


@pytest.mark.integration
class TestTextFieldsTruncationAndSafety:

    def test_tone_note_truncated_to_configured_max_chars(self, db_session, sample_brand):
        _upsert_config(db_session, "deck_brief_field_max_chars", "20")
        _make_essence(db_session, sample_brand.id, visual_strategy="x" * 100)
        brief = build_deck_brief(db_session, sample_brand.id)
        assert len(brief["tone_note"]) == 20

    def test_visual_strategy_as_dict_is_serialized_not_broken(self, db_session, sample_brand):
        _make_essence(db_session, sample_brand.id, visual_strategy={"summary": "bold and minimal"})
        brief = build_deck_brief(db_session, sample_brand.id)
        assert "bold and minimal" in brief["tone_note"]

    def test_opening_closing_hint_from_title_and_conclusion(self, db_session, sample_brand):
        _make_essence(
            db_session, sample_brand.id,
            slide_archetypes={
                "title": {"layout": "cover_hero"},
                "conclusion": "centered-dark",
            },
        )
        brief = build_deck_brief(db_session, sample_brand.id)
        assert "Opening: cover_hero" in brief["opening_closing_hint"]
        assert "Closing: centered-dark" in brief["opening_closing_hint"]
