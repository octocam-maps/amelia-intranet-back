"""Factoría de `IEmailSender` según `settings.email_provider`."""

from src.shared.config import get_settings
from src.shared.database import get_database_pool

from .mock_email_sender import MockEmailSender
from .sendgrid_email_sender import SendGridEmailSender
from .template_provider import PostgresEmailTemplateProvider


def get_email_sender():
    """`"mock"` (default) escribe en `email_log` sin red; `"sendgrid"` envía de
    verdad vía la API v3 de SendGrid. Cualquier otro valor de `EMAIL_PROVIDER`
    falla explícitamente en vez de silenciar el envío."""
    settings = get_settings()
    db_pool = get_database_pool()
    # Las plantillas editables (migración 041) se inyectan en AMBOS senders: así
    # lo que se ve en el log del mock es el mismo texto que enviaría SendGrid.
    template_provider = PostgresEmailTemplateProvider(db_pool)
    if settings.email_provider == "mock":
        return MockEmailSender(
            db_pool,
            frontend_url=settings.frontend_url,
            template_provider=template_provider,
        )
    if settings.email_provider == "sendgrid":
        return SendGridEmailSender(
            api_key=settings.sendgrid_api_key,
            from_email=settings.sendgrid_from_email,
            db_pool=db_pool,
            frontend_url=settings.frontend_url,
            template_provider=template_provider,
        )
    raise NotImplementedError(
        f"EMAIL_PROVIDER='{settings.email_provider}' no está implementado — "
        "usa 'mock' (default) o 'sendgrid'."
    )
