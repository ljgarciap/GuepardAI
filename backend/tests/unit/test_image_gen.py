import pytest
from unittest.mock import MagicMock, patch, ANY
import os

from providers.llm_provider import generate_ai_image

@pytest.fixture
def clean_uploads():
    # Setup: Clean or make sure uploads directory is created
    os.makedirs("uploads", exist_ok=True)
    yield
    # Cleanup: remove created test images if any (they are written as uploads/ai_v4_*.png)

@patch("providers.llm_provider.google_genai")
@patch("providers.llm_provider.genai_types")
@patch("providers.llm_provider.openai")
@patch("requests.get")
@patch("builtins.open")
def test_generate_ai_image_primary_success(mock_open, mock_get, mock_openai, mock_genai_types, mock_google_genai, clean_uploads):
    # Setup environment variables
    with patch.dict(os.environ, {"GOOGLE_API_KEY": "fake_google_key", "OPENAI_API_KEY": "fake_openai_key"}):
        # Mock Google GenAI response
        mock_client = MagicMock()
        mock_google_genai.Client.return_value = mock_client
        
        mock_response = MagicMock()
        mock_image = MagicMock()
        mock_image.image.image_bytes = b"fake_google_image_bytes"
        mock_response.generated_images = [mock_image]
        mock_client.models.generate_images.return_value = mock_response

        # Execute
        result = generate_ai_image("a futuristic city skyline")

        # Verify Google Client was called
        mock_google_genai.Client.assert_called_once_with(api_key="fake_google_key", http_options={'timeout': 600})
        mock_client.models.generate_images.assert_called_once()
        # Ensure DALL-E was NOT called
        mock_openai.OpenAI.assert_not_called()
        assert result is not None
        # Storage v1: las imágenes IA van al árbol de assets (público) de la marca
        assert os.path.basename(result).startswith("ai_v4_")
        assert "assets" in result.replace("\\", "/")

@patch("providers.llm_provider.google_genai")
@patch("providers.llm_provider.genai_types")
@patch("providers.llm_provider.openai")
@patch("requests.get")
@patch("builtins.open")
def test_generate_ai_image_fallback_success(mock_open, mock_get, mock_openai, mock_genai_types, mock_google_genai, clean_uploads):
    # Setup environment variables
    with patch.dict(os.environ, {"GOOGLE_API_KEY": "fake_google_key", "OPENAI_API_KEY": "fake_openai_key"}):
        # 1. Mock Google GenAI to raise exception (triggering fallback)
        mock_client = MagicMock()
        mock_google_genai.Client.return_value = mock_client
        mock_client.models.generate_images.side_effect = Exception("Google API Error")

        # 2. Mock OpenAI Client & DALL-E 3 response
        mock_openai_client = MagicMock()
        mock_openai.OpenAI.return_value = mock_openai_client
        
        mock_dalle_response = MagicMock()
        mock_image_data = MagicMock()
        mock_image_data.url = "http://fakeurl.com/image.png"
        mock_dalle_response.data = [mock_image_data]
        mock_openai_client.images.generate.return_value = mock_dalle_response

        # Mock requests.get response
        mock_requests_response = MagicMock()
        mock_requests_response.content = b"fake_dalle_image_bytes"
        mock_get.return_value = mock_requests_response

        # Execute
        result = generate_ai_image("a professional board meeting")

        # Verify Google Client was called and failed
        mock_google_genai.Client.assert_called_once()
        mock_client.models.generate_images.assert_called_once()
        
        # Verify DALL-E was called as fallback
        mock_openai.OpenAI.assert_called_once_with(api_key="fake_openai_key")
        mock_openai_client.images.generate.assert_called_once_with(
            model="dall-e-3",
            prompt=ANY,
            size="1792x1024",
            quality="standard",
            n=1
        )
        mock_get.assert_called_once_with("http://fakeurl.com/image.png")
        assert result is not None
        # Storage v1: las imágenes IA van al árbol de assets (público) de la marca
        assert os.path.basename(result).startswith("ai_v4_")
        assert "assets" in result.replace("\\", "/")

@patch("providers.llm_provider.google_genai")
@patch("providers.llm_provider.genai_types")
@patch("providers.llm_provider.openai")
def test_generate_ai_image_all_failed(mock_openai, mock_genai_types, mock_google_genai, clean_uploads):
    # Setup environment variables
    with patch.dict(os.environ, {"GOOGLE_API_KEY": "fake_google_key", "OPENAI_API_KEY": "fake_openai_key"}):
        # 1. Mock Google Client to fail
        mock_client = MagicMock()
        mock_google_genai.Client.return_value = mock_client
        mock_client.models.generate_images.side_effect = Exception("Google API Error")

        # 2. Mock OpenAI Client to fail
        mock_openai_client = MagicMock()
        mock_openai.OpenAI.return_value = mock_openai_client
        mock_openai_client.images.generate.side_effect = Exception("OpenAI API Error")

        # Execute
        result = generate_ai_image("a high-tech laboratory")

        # Verify both called
        mock_google_genai.Client.assert_called_once()
        mock_openai.OpenAI.assert_called_once()
        
        # Verify it returns None
        assert result is None
