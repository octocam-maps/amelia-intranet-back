"""Tests de `ListDocumentsUseCase` — alcance RGPD: empleado/socio solo ven
lo suyo; el administrador puede ver toda la plantilla o filtrar por
`user_id`."""

from datetime import datetime, timezone

import pytest

from src.features.documents.application.errors import (
    DocumentForbiddenError,
    InvalidDocumentCategoryError,
)
from src.features.documents.application.tests.fakes import FakeDocumentRepository
from src.features.documents.application.use_cases.list_documents import ListDocumentsUseCase
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
async def test_employee_sees_only_own_documents():
    repository = FakeDocumentRepository(
        [_document(id="doc-1", user_id="user-1"), _document(id="doc-2", user_id="user-2")]
    )
    use_case = ListDocumentsUseCase(repository)

    documents = await use_case.execute(requester_id="user-1", requester_role="empleado")

    assert [d.id for d in documents] == ["doc-1"]


@pytest.mark.asyncio
async def test_socio_sees_only_own_documents():
    repository = FakeDocumentRepository(
        [_document(id="doc-1", user_id="user-1"), _document(id="doc-2", user_id="user-2")]
    )
    use_case = ListDocumentsUseCase(repository)

    documents = await use_case.execute(requester_id="user-1", requester_role="socio")

    assert [d.id for d in documents] == ["doc-1"]


@pytest.mark.asyncio
async def test_employee_cannot_request_another_users_documents():
    repository = FakeDocumentRepository([_document(id="doc-1", user_id="user-1")])
    use_case = ListDocumentsUseCase(repository)

    with pytest.raises(DocumentForbiddenError):
        await use_case.execute(requester_id="user-1", requester_role="empleado", user_id="user-2")


@pytest.mark.asyncio
async def test_admin_without_user_id_sees_all_documents():
    repository = FakeDocumentRepository(
        [_document(id="doc-1", user_id="user-1"), _document(id="doc-2", user_id="user-2")]
    )
    use_case = ListDocumentsUseCase(repository)

    documents = await use_case.execute(requester_id="admin-1", requester_role="administrador")

    assert {d.id for d in documents} == {"doc-1", "doc-2"}


@pytest.mark.asyncio
async def test_admin_can_filter_by_user_id():
    repository = FakeDocumentRepository(
        [_document(id="doc-1", user_id="user-1"), _document(id="doc-2", user_id="user-2")]
    )
    use_case = ListDocumentsUseCase(repository)

    documents = await use_case.execute(
        requester_id="admin-1", requester_role="administrador", user_id="user-2"
    )

    assert [d.id for d in documents] == ["doc-2"]


@pytest.mark.asyncio
async def test_rejects_invalid_category():
    use_case = ListDocumentsUseCase(FakeDocumentRepository())

    with pytest.raises(InvalidDocumentCategoryError):
        await use_case.execute(requester_id="user-1", requester_role="empleado", category="invalid")


@pytest.mark.asyncio
async def test_excludes_soft_deleted_documents():
    now = datetime.now(timezone.utc)
    repository = FakeDocumentRepository([_document(id="doc-1", user_id="user-1", deleted_at=now)])
    use_case = ListDocumentsUseCase(repository)

    documents = await use_case.execute(requester_id="user-1", requester_role="empleado")

    assert documents == []
