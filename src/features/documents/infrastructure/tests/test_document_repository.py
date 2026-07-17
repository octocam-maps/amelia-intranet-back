"""Tests del adaptador `PostgresDocumentRepository` — verifica que las
queries usan los filtros correctos (RGPD: siempre `deleted_at IS NULL`,
scoping por `user_id`/`category`). Mismo patrón de mock de pool que
`features/absences/infrastructure/tests/test_absences_repository.py`: sin
Postgres real, un `AsyncMock` en el lugar del `DatabasePool`."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.features.documents.infrastructure.repositories.document_repository import (
    PostgresDocumentRepository,
)


def _row(**overrides) -> dict:
    now = datetime.now(timezone.utc)
    row = {
        "id": "doc-1",
        "user_id": "user-1",
        "category": "payslip",
        "title": "Nómina julio 2026",
        "period": "2026-07",
        "drive_file_id": "drive-1",
        "mime_type": "application/pdf",
        "content_hash": "hash-1",
        "uploaded_by": "admin-1",
        "uploaded_at": now,
        "created_at": now,
        "deleted_at": None,
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_list_for_user_filters_by_user_id_and_excludes_deleted():
    pool = AsyncMock()
    pool.fetch.return_value = [_row()]
    repository = PostgresDocumentRepository(pool)

    documents = await repository.list_for_user("user-1")

    assert documents[0].id == "doc-1"
    query, *params = pool.fetch.call_args[0]
    assert "user_id = $1" in query
    assert "deleted_at IS NULL" in query
    assert params == ["user-1", None]


@pytest.mark.asyncio
async def test_list_all_filters_by_category_and_user_id():
    pool = AsyncMock()
    pool.fetch.return_value = [_row()]
    repository = PostgresDocumentRepository(pool)

    await repository.list_all(category="payslip", user_id="user-1")

    query, *params = pool.fetch.call_args[0]
    assert "deleted_at IS NULL" in query
    assert params == ["payslip", "user-1"]


@pytest.mark.asyncio
async def test_create_inserts_metadata_row():
    pool = AsyncMock()
    pool.fetchrow.return_value = _row()
    repository = PostgresDocumentRepository(pool)

    document = await repository.create(
        user_id="user-1",
        category="payslip",
        title="Nómina julio 2026",
        period="2026-07",
        drive_file_id="drive-1",
        mime_type="application/pdf",
        content_hash="hash-1",
        uploaded_by="admin-1",
    )

    assert document.id == "doc-1"
    query = pool.fetchrow.call_args[0][0]
    assert "INSERT INTO employee_documents" in query


@pytest.mark.asyncio
async def test_soft_delete_returns_true_when_row_updated():
    pool = AsyncMock()
    pool.fetchrow.return_value = {"id": "doc-1"}
    repository = PostgresDocumentRepository(pool)

    deleted = await repository.soft_delete("doc-1")

    assert deleted is True
    query = pool.fetchrow.call_args[0][0]
    assert "deleted_at = CURRENT_TIMESTAMP" in query
    assert "deleted_at IS NULL" in query


@pytest.mark.asyncio
async def test_soft_delete_returns_false_when_already_deleted():
    pool = AsyncMock()
    pool.fetchrow.return_value = None
    repository = PostgresDocumentRepository(pool)

    deleted = await repository.soft_delete("doc-1")

    assert deleted is False


@pytest.mark.asyncio
async def test_find_by_id_excludes_soft_deleted():
    pool = AsyncMock()
    pool.fetchrow.return_value = None
    repository = PostgresDocumentRepository(pool)

    document = await repository.find_by_id("doc-1")

    assert document is None
    query = pool.fetchrow.call_args[0][0]
    assert "deleted_at IS NULL" in query


@pytest.mark.asyncio
async def test_save_and_find_drive_folder_id():
    pool = AsyncMock()
    pool.fetchval.return_value = "folder-abc"
    repository = PostgresDocumentRepository(pool)

    await repository.save_drive_folder_id("user-1", "folder-abc")
    folder_id = await repository.find_drive_folder_id("user-1")

    assert folder_id == "folder-abc"
    pool.execute.assert_awaited_once()
