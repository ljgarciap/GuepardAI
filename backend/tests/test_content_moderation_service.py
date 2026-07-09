"""
test_content_moderation_service.py — filtro de palabras determinista
(reviews-analitica-colaboracion, ítem 3).

Spec: docs/specs/reviews-analitica-colaboracion.md §3
"""
import json

import pytest

import models
from services.core import content_moderation_service


def _set_raw_value(db, value):
    """Upsert (no insert ciego): system_configs.key es único y — como los demás
    helpers de este suite que hacen db.commit() — una fila puede persistir entre
    tests si el commit rompe el aislamiento por rollback de la fixture."""
    cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == content_moderation_service.BLOCKLIST_CONFIG_KEY).first()
    if cfg is None:
        db.add(models.SystemConfig(key=content_moderation_service.BLOCKLIST_CONFIG_KEY, value=value))
    else:
        cfg.value = value
    db.commit()


def _set_blocklist(db, terms):
    _set_raw_value(db, json.dumps(terms))


@pytest.mark.integration
class TestEvaluate:

    def test_empty_text_is_visible(self, db_session):
        assert content_moderation_service.evaluate(db_session, "") == "visible"

    def test_no_blocklist_configured_is_visible(self, db_session):
        assert content_moderation_service.evaluate(db_session, "anything goes here") == "visible"

    def test_matches_blocklisted_term_case_insensitive(self, db_session):
        _set_blocklist(db_session, ["badword"])
        assert content_moderation_service.evaluate(db_session, "this has a BADWORD in it") == "flagged"

    def test_substring_match(self, db_session):
        _set_blocklist(db_session, ["spam"])
        assert content_moderation_service.evaluate(db_session, "this is spammy content") == "flagged"

    def test_no_match_stays_visible(self, db_session):
        _set_blocklist(db_session, ["badword"])
        assert content_moderation_service.evaluate(db_session, "this is a totally fine comment") == "visible"

    def test_malformed_config_value_tolerated(self, db_session):
        _set_raw_value(db_session, "not valid json")
        # No debe levantar excepción — degrada a blocklist vacía.
        assert content_moderation_service.evaluate(db_session, "anything") == "visible"

    def test_non_list_config_value_tolerated(self, db_session):
        _set_raw_value(db_session, json.dumps({"not": "a list"}))
        assert content_moderation_service.evaluate(db_session, "anything") == "visible"


@pytest.mark.integration
class TestGetBlocklist:

    def test_returns_terms_as_saved_not_lowercased(self, db_session):
        """get_blocklist() (usado por el editor del panel admin) debe devolver los
        términos tal cual se guardaron, no en minúsculas — la normalización para el
        matching pasa a lowercase solo dentro de evaluate()."""
        _set_blocklist(db_session, ["BadWord", "Spam"])
        assert content_moderation_service.get_blocklist(db_session) == ["BadWord", "Spam"]

    def test_empty_when_not_configured(self, db_session):
        assert content_moderation_service.get_blocklist(db_session) == []

    def test_blank_strings_filtered_out(self, db_session):
        _set_blocklist(db_session, ["real", "  ", ""])
        assert content_moderation_service.get_blocklist(db_session) == ["real"]
