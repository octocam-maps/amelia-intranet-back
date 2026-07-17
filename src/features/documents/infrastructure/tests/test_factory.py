"""
Tests de `get_document_storage` (`DRIVE_PROVIDER=mock|google|<inválido>`) —
mismo criterio que `get_email_sender`: rama mock construye de verdad, rama
google todavía no (WU-B), cualquier otro valor falla explícito.

Se sustituye `get_settings` por un fake simple (en vez de tocar la variable
de entorno + el `lru_cache` real de `Settings`) para no afectar a otros
tests que sí dependen del singleton cacheado.
"""

import pytest

from src.features.documents.infrastructure.factory import get_document_storage
from src.features.documents.infrastructure.providers.mock_drive_provider import (
    MockDocumentStorage,
)


class _FakeSettings:
    def __init__(self, drive_provider: str):
        self.drive_provider = drive_provider


def test_mock_provider_construye_mock_document_storage(monkeypatch):
    monkeypatch.setattr(
        "src.features.documents.infrastructure.factory.get_settings",
        lambda: _FakeSettings("mock"),
    )

    storage = get_document_storage()

    assert isinstance(storage, MockDocumentStorage)


def test_google_provider_todavia_no_implementado(monkeypatch):
    monkeypatch.setattr(
        "src.features.documents.infrastructure.factory.get_settings",
        lambda: _FakeSettings("google"),
    )

    with pytest.raises(NotImplementedError, match="google"):
        get_document_storage()


def test_provider_invalido_falla_explicito(monkeypatch):
    monkeypatch.setattr(
        "src.features.documents.infrastructure.factory.get_settings",
        lambda: _FakeSettings("aws-s3"),
    )

    with pytest.raises(NotImplementedError, match="aws-s3"):
        get_document_storage()
