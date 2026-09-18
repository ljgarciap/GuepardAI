"""
test_premium_visual_agent_vision_adjust_whitelist.py — Whitelist de implementabilidad
en la Iteración 2 del Premium Visual Agent (coherencia-artistica-pipeline.md, QA visual
del path premium).

Hallazgo: `normalize_executable_patterns()` (Task 1 del spec) filtra pattern_type no
implementados SOLO al momento de ingestión (cuando se persiste
`BrandPremiumVisualPattern.patterns_json`). `PremiumVisualAgent._vision_adjust_loop()`
hace una llamada LLM aparte (Iteración 2, `generate_premium_json`) y, antes de este fix,
aplicaba `adj["pattern_type"]` a la slide sin volver a pasar por la whitelist — un
pattern_type alucinado o no implementado (p. ej. "object_as_letter") se habría persistido
igual, y `premium_pdf.html` lo habría colapsado en silencio a `editorial_split` al
renderizar, exactamente el bug que motivó el spec, reintroducido en un segundo punto.
"""
import json

import pytest
from unittest.mock import patch

from services.rendering.premium_visual_agent import PremiumVisualAgent


def _upsert_config(db_session, key, value):
    import models
    rec = db_session.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if rec:
        rec.value = value
    else:
        db_session.add(models.SystemConfig(key=key, value=value, description="test"))
    db_session.flush()


def _agent(db_session, sample_job):
    return PremiumVisualAgent(db=db_session, job_id=sample_job.id, uploads_dir="/tmp/uploads")


def _base_patterns():
    return [
        {"pattern_type": "full_bleed_hero", "description": "Cover", "execution_hint": ""},
        {"pattern_type": "editorial_split", "description": "Default", "execution_hint": ""},
    ]


def _base_slides():
    return [
        {"slide_number": 1, "title": "Cover", "pattern_type": "full_bleed_hero"},
        {"slide_number": 2, "title": "Body", "pattern_type": "editorial_split"},
    ]


@pytest.mark.integration
class TestVisionAdjustLoopHonorsImplementabilityWhitelist:

    def test_implemented_pattern_type_adjustment_is_applied(self, db_session, sample_job):
        _upsert_config(db_session, "implemented_premium_patterns",
                        json.dumps(["full_bleed_hero", "data_cards_brand_grid", "editorial_split"]))
        agent = _agent(db_session, sample_job)
        slides = _base_slides()

        with patch("providers.llm_provider.generate_premium_json") as mock_premium:
            mock_premium.return_value = {
                "adjustments": [
                    {"slide_number": 2, "pattern_type": "data_cards_brand_grid", "reason": "Better fit"},
                ]
            }
            result = agent._vision_adjust_loop(slides, _base_patterns(), brand_dna=None, brand_assets={})

        assert result[1]["pattern_type"] == "data_cards_brand_grid"

    def test_unimplemented_pattern_type_adjustment_is_dropped_not_applied(self, db_session, sample_job):
        """
        Reproduce del hallazgo: el Vision LLM sugiere un pattern_type reconocido por
        SUPPORTED_PATTERN_TYPES pero SIN bloque real en premium_pdf.html. Antes del fix,
        esto sobreescribía silenciosamente el pattern_type correcto de Iteración 1.
        """
        _upsert_config(db_session, "implemented_premium_patterns",
                        json.dumps(["full_bleed_hero", "data_cards_brand_grid", "editorial_split"]))
        agent = _agent(db_session, sample_job)
        slides = _base_slides()

        with patch("providers.llm_provider.generate_premium_json") as mock_premium:
            mock_premium.return_value = {
                "adjustments": [
                    {"slide_number": 1, "pattern_type": "object_as_letter", "reason": "Creative treatment"},
                ]
            }
            result = agent._vision_adjust_loop(slides, _base_patterns(), brand_dna=None, brand_assets={})

        # La slide 1 conserva su pattern_type de Iteración 1 — el ajuste inválido se ignora.
        assert result[0]["pattern_type"] == "full_bleed_hero"

    def test_mixed_valid_and_invalid_adjustments_only_valid_ones_apply(self, db_session, sample_job):
        _upsert_config(db_session, "implemented_premium_patterns",
                        json.dumps(["full_bleed_hero", "data_cards_brand_grid", "editorial_split"]))
        agent = _agent(db_session, sample_job)
        slides = _base_slides()

        with patch("providers.llm_provider.generate_premium_json") as mock_premium:
            mock_premium.return_value = {
                "adjustments": [
                    {"slide_number": 1, "pattern_type": "typographic_substitution", "reason": "..."},
                    {"slide_number": 2, "pattern_type": "full_bleed_hero", "reason": "..."},
                ]
            }
            result = agent._vision_adjust_loop(slides, _base_patterns(), brand_dna=None, brand_assets={})

        assert result[0]["pattern_type"] == "full_bleed_hero"   # unchanged — invalid adjustment dropped
        assert result[1]["pattern_type"] == "full_bleed_hero"   # changed — valid adjustment applied

    def test_narrower_runtime_whitelist_also_blocks_a_normally_implemented_pattern(self, db_session, sample_job):
        # Si mañana se retira data_cards_brand_grid de implemented_premium_patterns
        # (regresión temporal en premium_pdf.html, por ejemplo), la Iteración 2 debe
        # respetarlo igual que la Iteración 1 — misma fuente de verdad.
        _upsert_config(db_session, "implemented_premium_patterns",
                        json.dumps(["full_bleed_hero", "editorial_split"]))
        agent = _agent(db_session, sample_job)
        slides = _base_slides()

        with patch("providers.llm_provider.generate_premium_json") as mock_premium:
            mock_premium.return_value = {
                "adjustments": [
                    {"slide_number": 2, "pattern_type": "data_cards_brand_grid", "reason": "..."},
                ]
            }
            result = agent._vision_adjust_loop(slides, _base_patterns(), brand_dna=None, brand_assets={})

        assert result[1]["pattern_type"] == "editorial_split"  # unchanged — dropped from whitelist right now

    def test_every_persisted_pattern_type_belongs_to_implemented_patterns(self, db_session, sample_job):
        """
        Criterio de aceptación de la spec: 'cada slide.pattern_type persistido pertenece
        a implemented_premium_patterns'. Exercita el loop completo con una mezcla
        deliberadamente hostil de ajustes (válidos, no implementados, e inexistentes en
        SUPPORTED_PATTERN_TYPES) y confirma la invariante sobre CADA slide resultante.
        """
        from services.ingestion.visual_pattern_service import get_implemented_premium_patterns

        implemented_list = ["full_bleed_hero", "data_cards_brand_grid", "editorial_split"]
        _upsert_config(db_session, "implemented_premium_patterns", json.dumps(implemented_list))
        agent = _agent(db_session, sample_job)
        slides = [
            {"slide_number": 1, "title": "Cover", "pattern_type": "full_bleed_hero"},
            {"slide_number": 2, "title": "Metrics", "pattern_type": "editorial_split"},
            {"slide_number": 3, "title": "Quote", "pattern_type": "editorial_split"},
        ]

        with patch("providers.llm_provider.generate_premium_json") as mock_premium:
            mock_premium.return_value = {
                "adjustments": [
                    {"slide_number": 2, "pattern_type": "data_cards_brand_grid", "reason": "Metrics fit"},
                    {"slide_number": 3, "pattern_type": "object_as_letter", "reason": "Hallucinated"},
                    {"slide_number": 99, "pattern_type": "brand_footer", "reason": "Non-existent slide"},
                ]
            }
            result = agent._vision_adjust_loop(slides, _base_patterns(), brand_dna=None, brand_assets={})

        implemented = get_implemented_premium_patterns(db=db_session)
        assert all(slide["pattern_type"] in implemented for slide in result)
        assert result[1]["pattern_type"] == "data_cards_brand_grid"  # valid adjustment applied
        assert result[2]["pattern_type"] == "editorial_split"        # invalid adjustment dropped
