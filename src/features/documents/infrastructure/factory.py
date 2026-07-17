"""Factoría de `IDocumentStorage` según `settings.drive_provider` — mismo
patrón que `src/shared/email/infrastructure/factory.get_email_sender`."""

from src.shared.config import get_settings

from ..domain.ports import IDocumentStorage
from .providers.google_drive_provider import GoogleDriveDocumentStorage
from .providers.mock_drive_provider import MockDocumentStorage


def get_document_storage() -> IDocumentStorage:
    """`"mock"` (default) — 100% en memoria, sin red ni credenciales; permite
    construir y testear el resto del feature sin depender de credenciales
    reales de Google. `"google"` es el proveedor real sobre una Unidad
    compartida (Shared Drive) — Service Account con acceso directo, SIN
    Domain-Wide Delegation (decisión posterior del usuario, ver engram #450
    y `GoogleDriveDocumentStorage`). Cualquier otro valor de `DRIVE_PROVIDER`
    falla explícito, igual que `get_email_sender`."""
    settings = get_settings()
    if settings.drive_provider == "mock":
        return MockDocumentStorage()
    if settings.drive_provider == "google":
        # Falla al construir si faltan credenciales/root folder (fail-fast,
        # ver `GoogleDriveDocumentStorage.__init__`) — no aquí en la
        # factoría, para no duplicar la validación.
        return GoogleDriveDocumentStorage(
            key_path=settings.google_service_account_key_path,
            key_json=settings.google_service_account_key_json,
            root_folder_id=settings.drive_root_folder_id,
        )
    raise NotImplementedError(
        f"DRIVE_PROVIDER='{settings.drive_provider}' no está implementado — "
        "usa 'mock' (default) o 'google'."
    )
