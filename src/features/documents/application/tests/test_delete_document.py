"""Tests de `DeleteDocumentUseCase` — soft-delete; NUNCA borra el binario
en Drive (Drive lo gestiona RRHH directamente)."""

from datetime import datetime, timezone

import pytest

from src.features.documents.application.errors import DocumentNotFoundError
from src.features.documents.application.tests.fakes import FakeDocumentRepository
from src.features.documents.application.use_cases.delete_document import DeleteDocumentUseCase
from src.features.documents.domain.models import Document


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
async def test_soft_deletes_document():
    repository = FakeDocumentRepository([_document()])
    use_case = DeleteDocumentUseCase(repository)

    await use_case.execute(document_id="doc-1")

    assert repository.documents["doc-1"].deleted_at is not None
    assert await repository.find_by_id("doc-1") is None


@pytest.mark.asyncio
async def test_raises_not_found_for_missing_document():
    use_case = DeleteDocumentUseCase(FakeDocumentRepository())

    with pytest.raises(DocumentNotFoundError):
        await use_case.execute(document_id="doc-inexistente")


@pytest.mark.asyncio
async def test_raises_not_found_for_already_deleted_document():
    now = datetime.now(timezone.utc)
    repository = FakeDocumentRepository([_document(deleted_at=now)])
    use_case = DeleteDocumentUseCase(repository)

    with pytest.raises(DocumentNotFoundError):
        await use_case.execute(document_id="doc-1")
