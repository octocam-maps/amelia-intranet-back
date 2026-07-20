"""Tests de `DownloadDocumentUseCase` — ownership RGPD: un empleado/socio
solo puede descargar sus propios documentos; el administrador puede
descargar cualquiera."""

from datetime import datetime, timezone

import pytest

from src.features.documents.application.errors import (
    DocumentForbiddenError,
    DocumentNotFoundError,
)
from src.features.documents.application.tests.fakes import (
    FakeDocumentRepository,
    FakeDocumentStorage,
)
from src.features.documents.application.use_cases.download_document import (
    DownloadDocumentUseCase,
)
from src.features.documents.domain.models import Document
from src.features.documents.domain.ports import DriveFileNotFoundError


def _document(**overrides) -> Document:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id="doc-1",
        user_id="user-1",
        category="payslip",
        title="Nómina julio 2026",
        period="2026-07",
        drive_file_id="drive-1",
        mime_type="application/pdf",
        content_hash="hash-1",
        uploaded_by="admin-1",
        uploaded_at=now,
        created_at=now,
        deleted_at=None,
    )
    defaults.update(overrides)
    return Document(**defaults)


@pytest.mark.asyncio
async def test_owner_can_download_own_document():
    repository = FakeDocumentRepository([_document()])
    storage = FakeDocumentStorage()
    storage.content_by_file_id["drive-1"] = b"%PDF-1.4 contenido"
    use_case = DownloadDocumentUseCase(repository, storage)

    result = await use_case.execute(
        document_id="doc-1", requester_id="user-1", requester_role="empleado"
    )

    assert result.content == b"%PDF-1.4 contenido"
    assert result.document.id == "doc-1"


@pytest.mark.asyncio
async def test_admin_can_download_any_document():
    repository = FakeDocumentRepository([_document(user_id="user-1")])
    storage = FakeDocumentStorage()
    storage.content_by_file_id["drive-1"] = b"contenido"
    use_case = DownloadDocumentUseCase(repository, storage)

    result = await use_case.execute(
        document_id="doc-1", requester_id="admin-1", requester_role="administrador"
    )

    assert result.content == b"contenido"


@pytest.mark.asyncio
async def test_blocks_download_of_another_users_document():
    repository = FakeDocumentRepository([_document(user_id="user-1")])
    storage = FakeDocumentStorage()
    use_case = DownloadDocumentUseCase(repository, storage)

    with pytest.raises(DocumentForbiddenError):
        await use_case.execute(document_id="doc-1", requester_id="user-2", requester_role="empleado")


@pytest.mark.asyncio
async def test_socio_blocked_from_downloading_another_users_document():
    repository = FakeDocumentRepository([_document(user_id="user-1")])
    storage = FakeDocumentStorage()
    use_case = DownloadDocumentUseCase(repository, storage)

    with pytest.raises(DocumentForbiddenError):
        await use_case.execute(document_id="doc-1", requester_id="user-2", requester_role="socio")


@pytest.mark.asyncio
async def test_raises_not_found_for_missing_document():
    use_case = DownloadDocumentUseCase(FakeDocumentRepository(), FakeDocumentStorage())

    with pytest.raises(DocumentNotFoundError):
        await use_case.execute(
            document_id="doc-inexistente", requester_id="user-1", requester_role="empleado"
        )


@pytest.mark.asyncio
async def test_raises_not_found_for_soft_deleted_document():
    now = datetime.now(timezone.utc)
    repository = FakeDocumentRepository([_document(deleted_at=now)])
    use_case = DownloadDocumentUseCase(repository, FakeDocumentStorage())

    with pytest.raises(DocumentNotFoundError):
        await use_case.execute(document_id="doc-1", requester_id="user-1", requester_role="empleado")


@pytest.mark.asyncio
async def test_propagates_drive_file_not_found_error():
    # Metadatos presentes en Postgres pero sin archivo real en el proveedor
    # activo — se deja propagar sin envolver (WU-C2 la mapea a 404, igual
    # que `DocumentNotFoundError`).
    repository = FakeDocumentRepository([_document()])
    storage = FakeDocumentStorage()  # sin contenido cargado para 'drive-1'
    use_case = DownloadDocumentUseCase(repository, storage)

    with pytest.raises(DriveFileNotFoundError):
        await use_case.execute(document_id="doc-1", requester_id="user-1", requester_role="empleado")
