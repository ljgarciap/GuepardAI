"""
email_service.py — Envío de email vía SMTP genérico (stdlib `smtplib`, sin
dependencia nueva). Infraestructura nueva para GuepardAI (reportes mensuales).

Sin proveedor SMTP configurado, `send_email` hace `log.warning` y no falla el
proceso que lo llama — mismo criterio de tolerancia que `SUPERADMIN_EMAIL`
("skipped, no blocking") en utils/seed_superadmin.py. Luis/DevOps eligen el
proveedor SMTP (SES, Gmail Workspace, SendGrid vía SMTP, etc.) al desplegar.

Spec: docs/specs/reviews-analitica-colaboracion.md
Design: docs/designs/reviews-analitica-colaboracion.md §6
"""
import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def _smtp_config() -> dict | None:
    host = os.getenv("EMAIL_SMTP_HOST")
    from_address = os.getenv("EMAIL_FROM_ADDRESS")
    if not host or not from_address:
        return None
    return {
        "host": host,
        "port": int(os.getenv("EMAIL_SMTP_PORT", "587")),
        "user": os.getenv("EMAIL_SMTP_USER"),
        "password": os.getenv("EMAIL_SMTP_PASSWORD"),
        "from_address": from_address,
    }


def send_email(to: str, subject: str, body: str) -> bool:
    """Envía un email de texto plano. Devuelve False (y loguea warning) si no hay
    SMTP configurado o si el envío falla — nunca levanta excepción al caller."""
    config = _smtp_config()
    if config is None:
        logger.warning(
            "[EmailService] EMAIL_SMTP_HOST/EMAIL_FROM_ADDRESS not configured — "
            "skipping send to %s (subject=%r)", to, subject,
        )
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config["from_address"]
    message["To"] = to
    message.set_content(body)

    try:
        with smtplib.SMTP(config["host"], config["port"], timeout=10) as smtp:
            smtp.starttls()
            if config["user"] and config["password"]:
                smtp.login(config["user"], config["password"])
            smtp.send_message(message)
        return True
    except Exception as e:
        logger.warning("[EmailService] Failed to send email to %s: %s", to, e)
        return False
