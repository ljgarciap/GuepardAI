import base64
import pytest
from unittest.mock import MagicMock, patch, ANY
import os

from providers.llm_provider import generate_ai_image


@pytest.fixture
def clean_uploads():
    os.makedirs("uploads", exist_ok=True)
    yield


@patch("providers.llm_provider.google_genai")
@patch("providers.llm_provider.genai_types")
@patch("providers.llm_provider.openai")
@patch("builtins.open")
def test_generate_ai_image_primary_success(mock_open, mock_openai, mock_genai_types, mock_google_genai, clean_uploads, tmp_path):
    with patch.dict(os.environ, {"GOOGLE_API_KEY": "fake_google_key", "OPENAI_API_KEY": "fake_openai_key"}), \
         patch("services.core.storage_service.brand_assets_dir", return_value=str(tmp_path)):

        mock_client = MagicMock()
        mock_google_genai.Client.return_value = mock_client
        mock_google_genai.__bool__ = lambda s: True

        mock_response = MagicMock()
        mock_image = MagicMock()
        mock_image.image.image_bytes = b"fake_google_image_bytes"
        mock_response.generated_images = [mock_image]
        mock_client.models.generate_images.return_value = mock_response

        result = generate_ai_image("a futuristic city skyline")

        # Tier 1 succeeds — Client called once, no http_options
        mock_google_genai.Client.assert_called_once_with(api_key="fake_google_key")
        mock_client.models.generate_images.assert_called_once()
        mock_openai.OpenAI.assert_not_called()
        assert result is not None
        assert os.path.basename(result).startswith("ai_v4_")


@patch("providers.llm_provider.google_genai")
@patch("providers.llm_provider.genai_types")
@patch("providers.llm_provider.openai")
@patch("builtins.open")
def test_generate_ai_image_fallback_success(mock_open, mock_openai, mock_genai_types, mock_google_genai, clean_uploads, tmp_path):
    with patch.dict(os.environ, {"GOOGLE_API_KEY": "fake_google_key", "OPENAI_API_KEY": "fake_openai_key"}), \
         patch("services.core.storage_service.brand_assets_dir", return_value=str(tmp_path)):

        # Both Google tiers fail
        mock_client = MagicMock()
        mock_google_genai.Client.return_value = mock_client
        mock_google_genai.__bool__ = lambda s: True
        mock_client.models.generate_images.side_effect = Exception("Google API Error")

        # gpt-image-1 returns b64_json (not a URL)
        mock_openai_client = MagicMock()
        mock_openai.OpenAI.return_value = mock_openai_client

        img_bytes = b"fake_gpt_image_bytes"
        mock_item = MagicMock()
        mock_item.b64_json = base64.b64encode(img_bytes).decode()
        mock_openai_response = MagicMock()
        mock_openai_response.data = [mock_item]
        mock_openai_client.images.generate.return_value = mock_openai_response

        result = generate_ai_image("a professional board meeting")

        # Both Google tier 1 and tier 2 were tried
        assert mock_google_genai.Client.call_count == 2
        # gpt-image-1 called as final fallback
        mock_openai.OpenAI.assert_called_once_with(api_key="fake_openai_key")
        mock_openai_client.images.generate.assert_called_once_with(
            model="gpt-image-1",
            prompt=ANY,
            size="1536x1024",
            quality="medium",
            n=1
        )
        assert result is not None
        assert os.path.basename(result).startswith("ai_v4_")


@patch("providers.llm_provider.google_genai")
@patch("providers.llm_provider.genai_types")
@patch("providers.llm_provider.openai")
def test_generate_ai_image_all_failed(mock_openai, mock_genai_types, mock_google_genai, clean_uploads):
    with patch.dict(os.environ, {"GOOGLE_API_KEY": "fake_google_key", "OPENAI_API_KEY": "fake_openai_key"}), \
         patch("services.core.storage_service.brand_assets_dir", return_value="/tmp"):

        mock_client = MagicMock()
        mock_google_genai.Client.return_value = mock_client
        mock_google_genai.__bool__ = lambda s: True
        mock_client.models.generate_images.side_effect = Exception("Google API Error")

        mock_openai_client = MagicMock()
        mock_openai.OpenAI.return_value = mock_openai_client
        mock_openai_client.images.generate.side_effect = Exception("OpenAI API Error")

        result = generate_ai_image("a high-tech laboratory")

        # Both Google tiers tried (tier1 + tier2 = 2 Client instantiations)
        assert mock_google_genai.Client.call_count == 2
        mock_openai.OpenAI.assert_called_once()
        assert result is None
