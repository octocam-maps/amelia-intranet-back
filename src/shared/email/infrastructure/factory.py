"""Factoría de `IEmailSender` según `settings.email_provider`."""

from src.shared.config import get_settings
from src.shared.database import get_database_pool

from .mock_email_sender import MockEmailSender


def get_email_sender():
    """`"mock"` (default) es el único proveedor implementado hoy. Cualquier
    otro valor de `EMAIL_PROVIDER` falla explícitamente en vez de silenciar
    el envío o, peor, intentar instanciar un adaptador real a medio hacer —
    ver `sendgrid_email_sender.py`."""
    settings = get_settings()
    if settings.email_provider == "mock":
        return MockEmailSender(get_database_pool())
    raise NotImplementedError(
        f"EMAIL_PROVIDER='{settings.email_provider}' no está implementado en esta "
        "fase — solo 'mock' está disponible (docs/requerimientos-amelia-intranet.pdf §6)."
    )
