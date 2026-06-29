"""
test_llm_provider.py — Unit tests for providers/llm_provider.py

Tests pure routing functions: resolve_provider, get_system_config, clean_json_string.
No real DB or LLM calls. All routing tests use patch.dict(os.environ) to isolate
from dev-machine API keys that would otherwise change routing outcomes.
"""
import os
import pytest
from unittest.mock import MagicMock, patch


# Baseline env that clears all LLM keys so routing is deterministic on any machine.
_NO_KEYS = {
    "ANTHROPIC_API_KEY": "",
    "MISTRAL_API_KEY": "",
    "GOOGLE_API_KEY": "",
    "GEMINI_API_KEY": "",
    "OPENAI_API_KEY": "",
    "OPENROUTER_API_KEY": "",
    "ACTIVE_LLM": "",
}


# ─────────────────────────────────────────────────────────────────────────────
# resolve_provider — pure routing function, reads only env vars
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestResolveProvider:

    def test_design_specialization_routes_to_anthropic(self):
        """design + ANTHROPIC_API_KEY → always routes to anthropic regardless of ACTIVE_LLM."""
        env = {**_NO_KEYS, "ANTHROPIC_API_KEY": "sk-ant-test", "MISTRAL_API_KEY": "mk-test"}
        with patch.dict(os.environ, env):
            from providers.llm_provider import resolve_provider
            result = resolve_provider("design")
        assert result == "anthropic"

    def test_design_specialization_without_anthropic_key_falls_through(self):
        """Without ANTHROPIC_API_KEY, design routing falls through to the next available provider."""
        env = {**_NO_KEYS, "MISTRAL_API_KEY": "mk-test"}
        with patch.dict(os.environ, env):
            from providers.llm_provider import resolve_provider
            result = resolve_provider("design")
        assert result == "mistral"

    def test_embedding_specialization_prefers_mistral_over_gemini(self):
        """embedding specialization: mistral wins over gemini when both keys present."""
        env = {**_NO_KEYS, "MISTRAL_API_KEY": "mk-test", "GOOGLE_API_KEY": "gk-test"}
        with patch.dict(os.environ, env):
            from providers.llm_provider import resolve_provider
            result = resolve_provider("embedding")
        assert result == "mistral"

    def test_active_llm_env_respected_for_general(self):
        """ACTIVE_LLM=gemini forces gemini routing even when mistral key is also present."""
        env = {**_NO_KEYS, "ACTIVE_LLM": "gemini", "GOOGLE_API_KEY": "gk-test", "MISTRAL_API_KEY": "mk-test"}
        with patch.dict(os.environ, env):
            from providers.llm_provider import resolve_provider
            result = resolve_provider()
        assert result == "gemini"

    def test_no_keys_raises_value_error(self):
        """No API keys → ValueError with a helpful message."""
        with patch.dict(os.environ, _NO_KEYS):
            from providers.llm_provider import resolve_provider
            with pytest.raises(ValueError):
                resolve_provider()

    def test_mistral_key_wins_without_active_llm(self):
        """ACTIVE_LLM unset → first available key (mistral priority) is used."""
        env = {**_NO_KEYS, "MISTRAL_API_KEY": "mk-test"}
        with patch.dict(os.environ, env):
            from providers.llm_provider import resolve_provider
            result = resolve_provider()
        assert result == "mistral"


# ─────────────────────────────────────────────────────────────────────────────
# get_system_config — ENV > DB > default priority chain
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGetSystemConfig:

    def test_env_var_takes_priority_over_db(self):
        """ENV var (uppercase key) is returned immediately; DB session is never opened."""
        with patch.dict(os.environ, {"MY_CONFIG_KEY": "env_value"}):
            with patch("providers.llm_provider.SessionLocal") as mock_session:
                from providers.llm_provider import get_system_config
                result = get_system_config("my_config_key", "default_value")

        assert result == "env_value"
        mock_session.assert_not_called()

    def test_db_fallback_when_no_env_var(self):
        """Without ENV var, the value stored in DB is returned."""
        mock_cfg = MagicMock()
        mock_cfg.value = "db_value"
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_cfg

        # Set key to empty string so the env check fails (falsy)
        with patch.dict(os.environ, {"MY_DB_KEY": ""}):
            with patch("providers.llm_provider.SessionLocal", return_value=db):
                from providers.llm_provider import get_system_config
                result = get_system_config("my_db_key", "default_value")

        assert result == "db_value"

    def test_default_returned_when_neither_env_nor_db(self):
        """ENV absent + DB returns None → the caller-supplied default is used."""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        with patch.dict(os.environ, {"MISSING_KEY": ""}):
            with patch("providers.llm_provider.SessionLocal", return_value=db):
                from providers.llm_provider import get_system_config
                result = get_system_config("missing_key", "fallback_default")

        assert result == "fallback_default"


# ─────────────────────────────────────────────────────────────────────────────
# clean_json_string — strips markdown fences, guards empty input
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestCleanJsonString:

    def test_strips_markdown_json_fences(self):
        """```json ... ``` wrapper is removed; inner content is preserved."""
        from providers.llm_provider import clean_json_string
        raw = '```json\n{"key": "value"}\n```'
        result = clean_json_string(raw)
        assert result == '{"key": "value"}'

    def test_strips_bare_code_fences(self):
        """``` ... ``` without language tag is also stripped."""
        from providers.llm_provider import clean_json_string
        raw = '```\n{"key": "value"}\n```'
        result = clean_json_string(raw)
        assert result == '{"key": "value"}'

    def test_empty_string_returns_empty_braces(self):
        """Empty input returns '{}' so callers can always safely json.loads()."""
        from providers.llm_provider import clean_json_string
        assert clean_json_string("") == "{}"

    def test_clean_string_passes_through_unchanged(self):
        """Already-clean JSON is returned as-is (no modification)."""
        from providers.llm_provider import clean_json_string
        clean = '{"already": "clean", "count": 3}'
        assert clean_json_string(clean) == clean
