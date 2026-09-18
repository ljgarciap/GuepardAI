"""
test_visual_pattern_service.py — Whitelist runtime de pattern_type implementados
(Coherencia Artística del Pipeline).

Cubre:
  - get_implemented_premium_patterns(): default duro sin config, lectura desde
    system_configs vía `db` (unit + integration).
  - normalize_executable_patterns(): descarta pattern_type reconocidos pero sin
    implementación real en premium_pdf.html (integration).

Spec: docs/specs/coherencia-artistica-pipeline.md (Acceptance criteria, filas
"renderable_premium_patterns" y "normalize_executable_patterns filtra...").
"""
import json

import pytest

from services.ingestion.visual_pattern_service import (
    DEFAULT_IMPLEMENTED_PREMIUM_PATTERNS,
    get_implemented_premium_patterns,
    normalize_executable_patterns,
)


def _upsert_config(db_session, key, value):
    """Idempotente: otros tests de la suite pueden haber commiteado configs vía SessionLocal."""
    import models
    rec = db_session.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if rec:
        rec.value = value
    else:
        db_session.add(models.SystemConfig(key=key, value=value, description="test"))
    db_session.flush()


# ─────────────────────────────────────────────────────────────────────────────
# UNIT: default duro sin sesión ni config en BD
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
class TestGetImplementedPremiumPatternsDefault:

    def test_default_without_db_or_config(self):
        # Sin `db` y sin la key seedeada (o test DB no disponible), el helper
        # nunca debe romper el flujo — cae al default duro de la spec.
        result = get_implemented_premium_patterns()
        assert result == set(DEFAULT_IMPLEMENTED_PREMIUM_PATTERNS)
        assert result == {"full_bleed_hero", "data_cards_brand_grid", "editorial_split"}


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION: lectura desde system_configs vía `db` (fixture de rollback)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration
class TestGetImplementedPremiumPatternsFromDb:

    def test_reads_seeded_default_via_db_session(self, db_session):
        _upsert_config(
            db_session,
            "implemented_premium_patterns",
            json.dumps(DEFAULT_IMPLEMENTED_PREMIUM_PATTERNS),
        )
        result = get_implemented_premium_patterns(db=db_session)
        assert result == set(DEFAULT_IMPLEMENTED_PREMIUM_PATTERNS)

    def test_activating_a_new_pattern_is_a_config_change_not_a_deploy(self, db_session):
        # El día que premium_pdf.html gane un bloque real para image_masked_title,
        # activarlo es cambiar este valor — no tocar código.
        _upsert_config(
            db_session,
            "implemented_premium_patterns",
            json.dumps(["full_bleed_hero", "data_cards_brand_grid", "editorial_split", "image_masked_title"]),
        )
        result = get_implemented_premium_patterns(db=db_session)
        assert "image_masked_title" in result

    def test_corrupt_config_falls_back_to_hard_default(self, db_session):
        _upsert_config(db_session, "implemented_premium_patterns", "not-json-at-all")
        result = get_implemented_premium_patterns(db=db_session)
        assert result == set(DEFAULT_IMPLEMENTED_PREMIUM_PATTERNS)

    def test_broken_db_session_falls_back_without_raising(self):
        # Senior Reviewer finding: una sesión rota (transacción abortada, etc.)
        # no debe propagar — la promesa del docstring es "nunca rompe el flujo".
        class _BrokenSession:
            def query(self, *args, **kwargs):
                raise RuntimeError("current transaction is aborted")

        result = get_implemented_premium_patterns(db=_BrokenSession())
        assert result == set(DEFAULT_IMPLEMENTED_PREMIUM_PATTERNS)


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION: normalize_executable_patterns() filtra contra la whitelist
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration
class TestNormalizeExecutablePatternsImplementabilityFilter:

    def test_recognized_but_unimplemented_pattern_type_is_dropped(self, db_session):
        _upsert_config(
            db_session,
            "implemented_premium_patterns",
            json.dumps(DEFAULT_IMPLEMENTED_PREMIUM_PATTERNS),
        )
        vision_result = {
            "executable_visual_patterns": [
                {"pattern_type": "object_as_letter", "description": "Letra sustituida por objeto de marca."},
                {"pattern_type": "full_bleed_hero", "description": "Imagen a sangre con overlay de texto."},
            ]
        }

        patterns = normalize_executable_patterns(vision_result, db=db_session)

        pattern_types = {p["pattern_type"] for p in patterns}
        assert "object_as_letter" not in pattern_types
        assert "full_bleed_hero" in pattern_types

    def test_all_unimplemented_yields_empty_list_not_exception(self, db_session):
        _upsert_config(
            db_session,
            "implemented_premium_patterns",
            json.dumps(DEFAULT_IMPLEMENTED_PREMIUM_PATTERNS),
        )
        vision_result = {
            "executable_visual_patterns": [
                {"pattern_type": "brand_footer", "description": "..."},
                {"pattern_type": "logo_locked_footer", "description": "..."},
            ]
        }

        patterns = normalize_executable_patterns(vision_result, db=db_session)
        assert patterns == []

    def test_expanding_whitelist_lets_a_previously_dropped_pattern_survive(self, db_session):
        _upsert_config(
            db_session,
            "implemented_premium_patterns",
            json.dumps(["full_bleed_hero", "data_cards_brand_grid", "editorial_split", "brand_footer"]),
        )
        vision_result = {
            "executable_visual_patterns": [
                {"pattern_type": "brand_footer", "description": "..."},
            ]
        }

        patterns = normalize_executable_patterns(vision_result, db=db_session)
        assert {p["pattern_type"] for p in patterns} == {"brand_footer"}
