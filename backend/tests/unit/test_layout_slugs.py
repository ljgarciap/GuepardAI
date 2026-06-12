"""
Fix 4: Verify layout slug vocabulary correction in prompts and code defaults.
"""
import pytest
from unittest.mock import MagicMock, patch


def _make_db_with_prompt(key, value):
    """Return a mock DB that returns the given prompt template for the given key."""
    db = MagicMock()
    config = MagicMock()
    config.value = value

    def query_side_effect(model):
        q = MagicMock()
        def filter_side_effect(*args, **kwargs):
            f = MagicMock()
            # Match the key from the filter call to decide what to return
            filter_args = str(args)
            if key in filter_args:
                f.first.return_value = config
            else:
                f.first.return_value = None
            return f
        q.filter.side_effect = filter_side_effect
        return q

    db.query.side_effect = query_side_effect
    return db


def test_analyst_v3_prompt_in_seed_uses_correct_slugs():
    """prompt_analyst_v3 in seed.py must not contain composition_* vocabulary."""
    from utils.seed import CONFIGS
    v3 = next((c for c in CONFIGS if c["key"] == "prompt_analyst_v3"), None)
    assert v3 is not None, "prompt_analyst_v3 must exist in seed CONFIGS"
    value = v3["value"]
    assert "composition_hero" not in value
    assert "composition_split" not in value
    assert "composition_pillars" not in value
    assert '"hero"' in value
    assert '"split"' in value
    assert '"pillars"' in value
    assert '"data_grid"' in value
    assert '"custom_canvas"' in value


def test_art_director_v3_prompt_in_seed_uses_correct_slugs():
    """prompt_art_director_v3 in seed.py must not reference composition_* layouts in its instructions."""
    from utils.seed import CONFIGS
    v3 = next((c for c in CONFIGS if c["key"] == "prompt_art_director_v3"), None)
    assert v3 is not None, "prompt_art_director_v3 must exist in seed CONFIGS"
    value = v3["value"]
    # Design instructions must use bare slugs
    assert "composition_split" not in value
    assert "composition_hero" not in value
    # Output format should still list valid slugs
    assert "hero" in value
    assert "split" in value


def test_existing_prompt_keys_not_modified():
    """Seeder must not modify v1 and v2 keys — they must remain unchanged."""
    from utils.seed import CONFIGS
    v2_analyst = next((c for c in CONFIGS if c["key"] == "prompt_analyst_v2"), None)
    assert v2_analyst is not None
    # v2 still uses the old vocabulary (untouched — existing DBs rely on it)
    assert "composition_hero" in v2_analyst["value"] or "composition_split" in v2_analyst["value"]


def test_analyst_service_fallback_chain_reads_v3_first(monkeypatch):
    """analyst_service.get_slide_visual_strategy must try prompt_analyst_v3 before v2."""
    import models
    from services.generation import analyst_service

    captured_keys = []

    original_query = None

    class FakeFilter:
        def __init__(self, key_used):
            self._key = key_used

        def first(self):
            captured_keys.append(self._key)
            return None  # All return None → triggers full fallback chain

    class FakeQuery:
        def filter(self, *args, **kwargs):
            # Extract the right-hand value from SQLAlchemy BinaryExpression (column == "value")
            key_val = None
            for arg in args:
                try:
                    key_val = arg.right.value  # BindParameter.value holds the actual string
                except AttributeError:
                    pass
            if key_val == "prompt_analyst_v3":
                return FakeFilter("v3")
            elif key_val == "prompt_analyst_v2":
                return FakeFilter("v2")
            elif key_val == "prompt_analyst_v1":
                return FakeFilter("v1")
            return FakeFilter("other")

    db = MagicMock()
    db.query.return_value = FakeQuery()

    slide = MagicMock()
    slide.slide_number = 1
    slide.title = "Test"
    slide.content_json = {"bullets": [], "rag_source": "ctx"}

    job = MagicMock()
    job.brand_id = 1

    # Will raise after prompts fail — that's OK, we only care about query order
    try:
        analyst_service.get_slide_visual_strategy(db, slide, job)
    except Exception:
        pass

    assert "v3" in captured_keys, "v3 must be queried first"
    v3_pos = captured_keys.index("v3")
    if "v2" in captured_keys:
        assert captured_keys.index("v2") > v3_pos


def test_art_director_default_grammar_type_is_split():
    """The fallback grammar_type default in art_director_service must be 'split', not 'composition_split'."""
    import ast, pathlib

    src = pathlib.Path("services/generation/art_director_service.py").read_text(encoding="utf-8")
    assert '"composition_split"' not in src, (
        "art_director_service.py must not use 'composition_split' as a default. "
        "Use 'split' (the correct grammar slug)."
    )
