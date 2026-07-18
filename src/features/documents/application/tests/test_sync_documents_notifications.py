"""Cableado de los disparadores `payslip_available`/`document_uploaded` en
`SyncDocumentsUseCase` (RF §6) — mismo mapeo categoría->tipo que
`UploadDocumentUseCase` (ver `document_notifications.notify_document_created`,
compartido), pero disparado desde la conciliación Drive -> Postgres. Un
archivo por empleado ya indexado (`existing_drive_file_ids`) nunca vuelve a
notificarse: el sync no lo vuelve a `create`."""

import pytest

from src.features.documents.application.tests.fakes import (
    FakeDocumentRepository,
    FakeDocumentStorage,
)
from src.features.documents.application.use_cases.sync_documents import SyncDocumentsUseCase


class _RecordingNotify:
    def __init__(self):
        self.calls: list[dict] = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)


async def _place_file_in_drive(
    storage: FakeDocumentStorage, *, email: str, filename: str, content: bytes
) -> None:
    folder_id = await storage.get_or_create_employee_folder(email)
    await storage.upload(
        folder_id=folder_id, filename=filename, content=content, mime_type="application/pdf"
    )


@pytest.mark.asyncio
async def test_sync_notifies_payslip_available_for_a_new_payslip_placed_in_the_category_folder():
    storage = FakeDocumentStorage()
    employee_folder = await storage.get_or_create_employee_folder("ana.garcia@ameliahub.com")
    payslip_folder = await storage.get_or_create_category_folder(employee_folder, "payslip")
    await storage.upload(
        folder_id=payslip_folder,
        filename="NOMINA_2026-07_Ana.pdf",
        content=b"nomina",
        mime_type="application/pdf",
    )
    repository = FakeDocumentRepository(active_users=[("user-1", "ana.garcia@ameliahub.com")])
    await repository.save_drive_folder_id("user-1", employee_folder)
    notify = _RecordingNotify()
    use_case = SyncDocumentsUseCase(repository, storage, 10, notify)

    await use_case.execute()

    assert len(notify.calls) == 1
    assert notify.calls[0]["type"] == "payslip_available"
    assert notify.calls[0]["recipient_ids"] == ["user-1"]


@pytest.mark.asyncio
async def test_sync_notifies_document_uploaded_for_the_loose_file_fallback():
    storage = FakeDocumentStorage()
    await _place_file_in_drive(
        storage, email="ana.garcia@ameliahub.com", filename="CONTRATO_Ana.pdf", content=b"contrato"
    )
    repository = FakeDocumentRepository(active_users=[("user-1", "ana.garcia@ameliahub.com")])
    notify = _RecordingNotify()
    use_case = SyncDocumentsUseCase(repository, storage, 10, notify)

    await use_case.execute()

    assert len(notify.calls) == 1
    assert notify.calls[0]["type"] == "document_uploaded"
    assert notify.calls[0]["recipient_ids"] == ["user-1"]


@pytest.mark.asyncio
async def test_sync_does_not_renotify_a_file_that_was_already_indexed():
    storage = FakeDocumentStorage()
    existing_drive_file_id = None
    folder_id = await storage.get_or_create_employee_folder("ana.garcia@ameliahub.com")
    uploaded = await storage.upload(
        folder_id=folder_id,
        filename="CONTRATO_Ana.pdf",
        content=b"contrato",
        mime_type="application/pdf",
    )
    existing_drive_file_id = uploaded.drive_file_id

    from datetime import datetime, timezone

    from src.features.documents.domain.models import Document

    existing_document = Document(
        id="doc-existing",
        user_id="user-1",
        category="contract",
        title="CONTRATO_Ana.pdf",
        period=None,
        drive_file_id=existing_drive_file_id,
        mime_type="application/pdf",
        content_hash="hash-existing",
        uploaded_by=None,
        uploaded_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    repository = FakeDocumentRepository(
        [existing_document], active_users=[("user-1", "ana.garcia@ameliahub.com")]
    )
    await repository.save_drive_folder_id("user-1", folder_id)
    notify = _RecordingNotify()
    use_case = SyncDocumentsUseCase(repository, storage, 10, notify)

    await use_case.execute()

    assert notify.calls == []


@pytest.mark.asyncio
async def test_sync_without_a_notify_dependency_still_works():
    storage = FakeDocumentStorage()
    await _place_file_in_drive(
        storage, email="ana.garcia@ameliahub.com", filename="CONTRATO_Ana.pdf", content=b"contrato"
    )
    repository = FakeDocumentRepository(active_users=[("user-1", "ana.garcia@ameliahub.com")])
    use_case = SyncDocumentsUseCase(repository, storage, 10)

    sync_run = await use_case.execute()

    assert sync_run.files_synced == 1
