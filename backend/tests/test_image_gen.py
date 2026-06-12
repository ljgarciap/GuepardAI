"""
Fix 3: 3-tier image generation routing tests.
Verifies tier waterfall (fast → standard → gpt-image-1) and that
the old DALL-E 3 / URL-fetch pattern is gone.
"""
import base64
from unittest.mock import MagicMock, patch


# ─────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────

def _fake_imagen_response(img_bytes: bytes = b"PNG_BYTES"):
    resp = MagicMock()
    img = MagicMock()
    img.image.image_bytes = img_bytes
    resp.generated_images = [img]
    return resp


def _fake_gpt_image_response(img_bytes: bytes = b"PNG_BYTES"):
    resp = MagicMock()
    item = MagicMock()
    item.b64_json = base64.b64encode(img_bytes).decode()
    resp.data = [item]
    return resp


# ─────────────────────────────────────────────────────
# Tier 1 succeeds → returns immediately, never calls Tier 2 or 3
# ─────────────────────────────────────────────────────

def test_tier1_success_returns_path(tmp_path):
    with patch("providers.llm_provider.google_genai") as mock_genai, \
         patch("providers.llm_provider.genai_types") as mock_types, \
         patch("providers.llm_provider.os.getenv", side_effect=lambda k, d=None: "FAKE_KEY" if "GOOGLE" in k or "GEMINI" in k else d), \
         patch("services.core.storage_service.brand_assets_dir", return_value=str(tmp_path)):

        from providers.llm_provider import generate_ai_image

        mock_genai.__bool__ = lambda s: True
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_client.models.generate_images.return_value = _fake_imagen_response()
        mock_types.GenerateImagesConfig = MagicMock()

        result = generate_ai_image("executive meeting", brand_id=1)

        assert result is not None
        assert str(tmp_path) in result
        # Only called once (Tier 1)
        assert mock_client.models.generate_images.call_count == 1


def test_tier1_no_http_options(tmp_path):
    """Tier 1 must NOT pass http_options to Client (causes ReadTimeout)."""
    with patch("providers.llm_provider.google_genai") as mock_genai, \
         patch("providers.llm_provider.genai_types") as mock_types, \
         patch("providers.llm_provider.os.getenv", side_effect=lambda k, d=None: "FAKE_KEY" if "GOOGLE" in k or "GEMINI" in k else d), \
         patch("services.core.storage_service.brand_assets_dir", return_value=str(tmp_path)):

        from providers.llm_provider import generate_ai_image

        mock_genai.__bool__ = lambda s: True
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_client.models.generate_images.return_value = _fake_imagen_response()
        mock_types.GenerateImagesConfig = MagicMock()

        generate_ai_image("office scene", brand_id=None)

        # Verify Client was called without http_options
        call_kwargs = mock_genai.Client.call_args_list[0]
        assert "http_options" not in call_kwargs.kwargs, (
            "http_options must NOT be passed to Client — it causes ReadTimeout"
        )


# ─────────────────────────────────────────────────────
# Tier 1 fails → falls to Tier 2
# ─────────────────────────────────────────────────────

def test_tier2_called_when_tier1_fails(tmp_path):
    call_count = 0

    def imagen_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("quota exceeded")
        return _fake_imagen_response()

    with patch("providers.llm_provider.google_genai") as mock_genai, \
         patch("providers.llm_provider.genai_types") as mock_types, \
         patch("providers.llm_provider.os.getenv", side_effect=lambda k, d=None: "FAKE_KEY" if "GOOGLE" in k or "GEMINI" in k else d), \
         patch("services.core.storage_service.brand_assets_dir", return_value=str(tmp_path)):

        from providers.llm_provider import generate_ai_image

        mock_genai.__bool__ = lambda s: True
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_client.models.generate_images.side_effect = imagen_side_effect
        mock_types.GenerateImagesConfig = MagicMock()

        result = generate_ai_image("conference room", brand_id=1)

        assert result is not None
        assert call_count == 2, "Tier 2 must be called after Tier 1 fails"


# ─────────────────────────────────────────────────────
# Tier 1+2 fail → falls to Tier 3 (gpt-image-1, b64_json)
# ─────────────────────────────────────────────────────

def test_tier3_called_when_google_fails(tmp_path):
    with patch("providers.llm_provider.google_genai") as mock_genai, \
         patch("providers.llm_provider.genai_types") as mock_types, \
         patch("providers.llm_provider.openai") as mock_openai, \
         patch("providers.llm_provider.os.getenv") as mock_getenv, \
         patch("services.core.storage_service.brand_assets_dir", return_value=str(tmp_path)):

        def getenv_side_effect(k, d=None):
            if "GOOGLE" in k or "GEMINI" in k:
                return "FAKE_GEM_KEY"
            if "OPENAI" in k:
                return "FAKE_OAI_KEY"
            return d

        mock_getenv.side_effect = getenv_side_effect

        from providers.llm_provider import generate_ai_image

        mock_genai.__bool__ = lambda s: True
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_client.models.generate_images.side_effect = Exception("All google tiers failed")
        mock_types.GenerateImagesConfig = MagicMock()

        # gpt-image-1 returns b64_json
        mock_oai_client = MagicMock()
        mock_openai.OpenAI.return_value = mock_oai_client
        mock_oai_client.images.generate.return_value = _fake_gpt_image_response()

        result = generate_ai_image("product launch", brand_id=1)

        assert result is not None
        mock_oai_client.images.generate.assert_called_once()
        call_kwargs = mock_oai_client.images.generate.call_args.kwargs
        assert call_kwargs["model"] == "gpt-image-1"
        assert call_kwargs["size"] == "1536x1024"
        assert call_kwargs["quality"] == "medium"


def test_tier3_decodes_base64_not_url(tmp_path):
    """gpt-image-1 returns b64_json — must decode, must NOT call requests.get."""
    with patch("providers.llm_provider.google_genai") as mock_genai, \
         patch("providers.llm_provider.genai_types") as mock_types, \
         patch("providers.llm_provider.openai") as mock_openai, \
         patch("providers.llm_provider.os.getenv") as mock_getenv, \
         patch("services.core.storage_service.brand_assets_dir", return_value=str(tmp_path)):

        def getenv_side_effect(k, d=None):
            if "GOOGLE" in k or "GEMINI" in k:
                return "FAKE_GEM_KEY"
            if "OPENAI" in k:
                return "FAKE_OAI_KEY"
            return d

        mock_getenv.side_effect = getenv_side_effect

        from providers.llm_provider import generate_ai_image

        mock_genai.__bool__ = lambda s: True
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_client.models.generate_images.side_effect = Exception("quota")
        mock_types.GenerateImagesConfig = MagicMock()

        expected_bytes = b"\x89PNG\r\nFAKE"
        mock_oai_client = MagicMock()
        mock_openai.OpenAI.return_value = mock_oai_client
        mock_oai_client.images.generate.return_value = _fake_gpt_image_response(expected_bytes)

        result = generate_ai_image("skyline", brand_id=1)

        assert result is not None
        with open(result, "rb") as f:
            saved = f.read()
        assert saved == expected_bytes, "Saved bytes must match decoded b64_json"


# ─────────────────────────────────────────────────────
# All tiers fail → returns None
# ─────────────────────────────────────────────────────

def test_all_tiers_fail_returns_none(tmp_path):
    with patch("providers.llm_provider.google_genai") as mock_genai, \
         patch("providers.llm_provider.genai_types") as mock_types, \
         patch("providers.llm_provider.openai") as mock_openai, \
         patch("providers.llm_provider.os.getenv") as mock_getenv, \
         patch("services.core.storage_service.brand_assets_dir", return_value=str(tmp_path)):

        def getenv_side_effect(k, d=None):
            if "GOOGLE" in k or "GEMINI" in k:
                return "FAKE_GEM_KEY"
            if "OPENAI" in k:
                return "FAKE_OAI_KEY"
            return d

        mock_getenv.side_effect = getenv_side_effect

        from providers.llm_provider import generate_ai_image

        mock_genai.__bool__ = lambda s: True
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_client.models.generate_images.side_effect = Exception("all fail")
        mock_types.GenerateImagesConfig = MagicMock()

        mock_oai_client = MagicMock()
        mock_openai.OpenAI.return_value = mock_oai_client
        mock_oai_client.images.generate.side_effect = Exception("OpenAI also fails")

        result = generate_ai_image("abstract", brand_id=1)

        assert result is None


# ─────────────────────────────────────────────────────
# Confirm DALL-E 3 and URL-fetch pattern are gone
# ─────────────────────────────────────────────────────

def test_no_dalle3_in_source():
    """The old DALL-E 3 / requests.get(image_url) pattern must not exist."""
    import inspect
    from providers import llm_provider
    source = inspect.getsource(llm_provider.generate_ai_image)
    assert "dall-e-3" not in source, "dall-e-3 must be removed from generate_ai_image"
    assert "1792x1024" not in source, "1792x1024 (DALL-E 3 size) must be removed"
    assert "requests.get" not in source, "requests.get(image_url) URL-fetch must be removed"
