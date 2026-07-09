"""
test_email_service.py — envío de email tolerante (reviews-analitica-colaboracion,
ítem 6/7). Sin BD — mockea smtplib y las env vars.
"""
from unittest.mock import MagicMock, patch

from services.core import email_service


def _clear_smtp_env(monkeypatch):
    for key in ("EMAIL_SMTP_HOST", "EMAIL_SMTP_PORT", "EMAIL_SMTP_USER", "EMAIL_SMTP_PASSWORD", "EMAIL_FROM_ADDRESS"):
        monkeypatch.delenv(key, raising=False)


def test_returns_false_without_raising_when_not_configured(monkeypatch):
    _clear_smtp_env(monkeypatch)
    result = email_service.send_email("someone@example.com", "Subject", "Body")
    assert result is False


def test_missing_from_address_alone_also_disables_sending(monkeypatch):
    _clear_smtp_env(monkeypatch)
    monkeypatch.setenv("EMAIL_SMTP_HOST", "smtp.example.com")
    # EMAIL_FROM_ADDRESS sigue sin setear
    result = email_service.send_email("someone@example.com", "Subject", "Body")
    assert result is False


def test_sends_via_smtp_when_configured(monkeypatch):
    _clear_smtp_env(monkeypatch)
    monkeypatch.setenv("EMAIL_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("EMAIL_FROM_ADDRESS", "noreply@guepardai.com")

    mock_smtp_instance = MagicMock()
    mock_smtp_ctx = MagicMock()
    mock_smtp_ctx.__enter__.return_value = mock_smtp_instance
    mock_smtp_ctx.__exit__.return_value = False

    with patch("smtplib.SMTP", return_value=mock_smtp_ctx) as mock_smtp_cls:
        result = email_service.send_email("someone@example.com", "Subject", "Body")

    assert result is True
    mock_smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=10)
    mock_smtp_instance.starttls.assert_called_once()
    mock_smtp_instance.send_message.assert_called_once()


def test_login_skipped_when_no_credentials(monkeypatch):
    _clear_smtp_env(monkeypatch)
    monkeypatch.setenv("EMAIL_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("EMAIL_FROM_ADDRESS", "noreply@guepardai.com")

    mock_smtp_instance = MagicMock()
    mock_smtp_ctx = MagicMock()
    mock_smtp_ctx.__enter__.return_value = mock_smtp_instance
    mock_smtp_ctx.__exit__.return_value = False

    with patch("smtplib.SMTP", return_value=mock_smtp_ctx):
        email_service.send_email("someone@example.com", "Subject", "Body")

    mock_smtp_instance.login.assert_not_called()


def test_login_called_when_credentials_present(monkeypatch):
    _clear_smtp_env(monkeypatch)
    monkeypatch.setenv("EMAIL_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("EMAIL_FROM_ADDRESS", "noreply@guepardai.com")
    monkeypatch.setenv("EMAIL_SMTP_USER", "user")
    monkeypatch.setenv("EMAIL_SMTP_PASSWORD", "pass")

    mock_smtp_instance = MagicMock()
    mock_smtp_ctx = MagicMock()
    mock_smtp_ctx.__enter__.return_value = mock_smtp_instance
    mock_smtp_ctx.__exit__.return_value = False

    with patch("smtplib.SMTP", return_value=mock_smtp_ctx):
        email_service.send_email("someone@example.com", "Subject", "Body")

    mock_smtp_instance.login.assert_called_once_with("user", "pass")


def test_smtp_exception_returns_false_without_raising(monkeypatch):
    _clear_smtp_env(monkeypatch)
    monkeypatch.setenv("EMAIL_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("EMAIL_FROM_ADDRESS", "noreply@guepardai.com")

    with patch("smtplib.SMTP", side_effect=ConnectionRefusedError("boom")):
        result = email_service.send_email("someone@example.com", "Subject", "Body")

    assert result is False


def test_custom_port_is_respected(monkeypatch):
    _clear_smtp_env(monkeypatch)
    monkeypatch.setenv("EMAIL_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("EMAIL_FROM_ADDRESS", "noreply@guepardai.com")
    monkeypatch.setenv("EMAIL_SMTP_PORT", "2525")

    mock_smtp_ctx = MagicMock()
    mock_smtp_ctx.__enter__.return_value = MagicMock()
    mock_smtp_ctx.__exit__.return_value = False

    with patch("smtplib.SMTP", return_value=mock_smtp_ctx) as mock_smtp_cls:
        email_service.send_email("someone@example.com", "Subject", "Body")

    mock_smtp_cls.assert_called_once_with("smtp.example.com", 2525, timeout=10)
