"""Factoría de `IDocumentStorage` según `settings.drive_provider` — mismo
patrón que `src/shared/email/infrastructure/factory.get_email_sender`."""

from src.shared.config import get_settings

from ..domain.ports import IDocumentStorage
from .providers.mock_drive_provider import MockDocumentStorage


def get_document_storage() -> IDocumentStorage:
    """`"mock"` (default) — 100% en memoria, sin red ni credenciales; permite
    construir y testear el resto del feature sin depender de la aprobación
    de Domain-Wide Delegation a nivel de Workspace (ver
    `sdd/fase4-nominas-documentos/design`, Open Questions). `"google"` es el
    proveedor real (Service Account + DWD) — su implementación llega en la
    siguiente work-unit (WU-B); activarlo hoy falla explícito en vez de
    arrancar a medias. Cualquier otro valor de `DRIVE_PROVIDER` también
    falla explícito, igual que `get_email_sender`."""
    settings = get_settings()
    if settings.drive_provider == "mock":
        return MockDocumentStorage()
    if settings.drive_provider == "google":
        raise NotImplementedError(
            "DRIVE_PROVIDER='google' todavía no está implementado — el "
            "proveedor real de Google Drive llega en la work-unit B de "
            "`sdd/fase4-nominas-documentos`. Usa DRIVE_PROVIDER=mock "
            "(default) mientras tanto."
        )
    raise NotImplementedError(
        f"DRIVE_PROVIDER='{settings.drive_provider}' no está implementado — "
        "usa 'mock' (default) o 'google'."
    )
