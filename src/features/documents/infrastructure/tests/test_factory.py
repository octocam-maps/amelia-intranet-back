"""
Tests de `get_document_storage` (`DRIVE_PROVIDER=mock|google|<inválido>`) —
mismo criterio que `get_email_sender`: rama mock construye de verdad, rama
google (WU-B) también construye de verdad si hay credenciales/root folder
y falla explícito (fail-fast) si faltan, cualquier otro valor falla
explícito.

Se sustituye `get_settings` por un fake simple (en vez de tocar la variable
de entorno + el `lru_cache` real de `Settings`) para no afectar a otros
tests que sí dependen del singleton cacheado.
"""

import pytest

from src.features.documents.infrastructure.factory import get_document_storage
from src.features.documents.infrastructure.providers.google_drive_provider import (
    GoogleDriveDocumentStorage,
)
from src.features.documents.infrastructure.providers.mock_drive_provider import (
    MockDocumentStorage,
)


class _FakeSettings:
    def __init__(
        self,
        drive_provider: str,
        *,
        drive_root_folder_id: str = "",
        google_service_account_key_path: str = "",
        google_service_account_key_json: str = "",
    ):
        self.drive_provider = drive_provider
        self.drive_root_folder_id = drive_root_folder_id
        self.google_service_account_key_path = google_service_account_key_path
        self.google_service_account_key_json = google_service_account_key_json


def test_mock_provider_construye_mock_document_storage(monkeypatch):
    monkeypatch.setattr(
        "src.features.documents.infrastructure.factory.get_settings",
        lambda: _FakeSettings("mock"),
    )

    storage = get_document_storage()

    assert isinstance(storage, MockDocumentStorage)


def test_google_provider_pasa_las_credenciales_correctas_a_google_drive_document_storage(
    monkeypatch,
):
    # La factoría solo decide QUÉ clase construir y con qué argumentos —
    # cómo `GoogleDriveDocumentStorage` construye credenciales/`Resource`
    # reales (sin red) ya está cubierto en `test_google_drive_provider.py` /
    # `test_google_drive_client.py`. Aquí se sustituye la clase entera para
    # no depender de credenciales con formato válido.
    captured: dict = {}

    class _FakeGoogleDriveDocumentStorage:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "src.features.documents.infrastructure.factory.get_settings",
        lambda: _FakeSettings(
            "google",
            drive_root_folder_id="root-folder-123",
            google_service_account_key_json='{"type": "service_account"}',
        ),
    )
    monkeypatch.setattr(
        "src.features.documents.infrastructure.factory.GoogleDriveDocumentStorage",
        _FakeGoogleDriveDocumentStorage,
    )

    storage = get_document_storage()

    assert isinstance(storage, _FakeGoogleDriveDocumentStorage)
    assert captured == {
        "key_path": "",
        "key_json": '{"type": "service_account"}',
        "root_folder_id": "root-folder-123",
    }


def test_google_provider_sin_root_folder_id_falla_explicito(monkeypatch):
    monkeypatch.setattr(
        "src.features.documents.infrastructure.factory.get_settings",
        lambda: _FakeSettings(
            "google",
            drive_root_folder_id="",
            google_service_account_key_json='{"type": "service_account"}',
        ),
    )

    with pytest.raises(ValueError, match="DRIVE_ROOT_FOLDER_ID"):
        get_document_storage()


def test_google_provider_sin_credenciales_falla_explicito(monkeypatch):
    monkeypatch.setattr(
        "src.features.documents.infrastructure.factory.get_settings",
        lambda: _FakeSettings("google", drive_root_folder_id="root-folder-123"),
    )

    with pytest.raises(ValueError, match="Service Account"):
        get_document_storage()


def test_provider_invalido_falla_explicito(monkeypatch):
    monkeypatch.setattr(
        "src.features.documents.infrastructure.factory.get_settings",
        lambda: _FakeSettings("aws-s3"),
    )

    with pytest.raises(NotImplementedError, match="aws-s3"):
        get_document_storage()
