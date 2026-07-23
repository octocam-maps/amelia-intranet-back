"""Tests de `ProvisionEmployeeDriveFolderUseCase` — núcleo idempotente que
resuelve/crea la carpeta PADRE de Drive de un empleado y la cachea en
`users.drive_folder_id` (migración 025). Lo reusan tanto el hook del alta
(`CreateStaffMemberUseCase`) como el batch de backfill
(`BulkProvisionDriveFoldersUseCase`) — mismo criterio que
`notify_document_created` compartido entre `UploadDocumentUseCase` y
`SyncDocumentsUseCase`."""

import pytest

from src.features.documents.application.tests.fakes import (
    FakeDocumentRepository,
    FakeDocumentStorage,
)
from src.features.documents.application.use_cases.provision_employee_drive_folder import (
    ProvisionEmployeeDriveFolderUseCase,
)


class _CountingStorage(FakeDocumentStorage):
    """Instrumenta `get_or_create_employee_folder` para poder aseverar que
    el caso de uso NO llama a Drive cuando el id ya está cacheado — el resto
    de `FakeDocumentStorage` no expone un contador para este método."""

    def __init__(self):
        super().__init__()
        self.get_or_create_calls = 0

    async def get_or_create_employee_folder(self, email: str) -> str:
        self.get_or_create_calls += 1
        return await super().get_or_create_employee_folder(email)


def _use_case(*, repository=None, storage=None):
    repository = repository or FakeDocumentRepository()
    storage = storage or _CountingStorage()
    return ProvisionEmployeeDriveFolderUseCase(repository, storage), repository, storage


@pytest.mark.asyncio
async def test_noop_when_user_already_has_a_cached_folder():
    repository = FakeDocumentRepository()
    await repository.save_drive_folder_id("user-1", "existing-folder-id")
    use_case, repository, storage = _use_case(repository=repository)

    result = await use_case.execute(user_id="user-1", email="ana.garcia@ameliahub.com")

    assert result.created is False
    assert result.drive_folder_id == "existing-folder-id"
    assert storage.get_or_create_calls == 0  # nunca llama a Drive


@pytest.mark.asyncio
async def test_creates_and_caches_the_folder_when_missing():
    use_case, repository, storage = _use_case()

    result = await use_case.execute(user_id="user-1", email="ana.garcia@ameliahub.com")

    assert result.created is True
    assert result.drive_folder_id is not None
    assert storage.get_or_create_calls == 1
    assert await repository.find_drive_folder_id("user-1") == result.drive_folder_id


@pytest.mark.asyncio
async def test_is_idempotent_across_repeated_executions():
    """Re-ejecutar el caso de uso para el mismo empleado no debe volver a
    llamar a Drive ni duplicar el id cacheado — es lo que hace re-ejecutable
    al batch de backfill (retry seguro)."""
    use_case, repository, storage = _use_case()

    first = await use_case.execute(user_id="user-1", email="ana.garcia@ameliahub.com")
    second = await use_case.execute(user_id="user-1", email="ana.garcia@ameliahub.com")

    assert first.created is True
    assert second.created is False
    assert second.drive_folder_id == first.drive_folder_id
    assert storage.get_or_create_calls == 1
