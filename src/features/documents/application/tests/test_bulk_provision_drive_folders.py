"""Tests de `BulkProvisionDriveFoldersUseCase` — batch de backfill (admin,
`POST /documents/provision-folders`): provisiona la carpeta de Drive de cada
empleado ACTIVO que todavía no la tenga cacheada, reusando el núcleo
idempotente `ProvisionEmployeeDriveFolderUseCase`. Re-ejecutable (sirve de
retry) y best-effort por empleado (mismo criterio que `SyncDocumentsUseCase`)."""

import pytest

from src.features.documents.application.tests.fakes import (
    FakeDocumentRepository,
    FakeDocumentStorage,
)
from src.features.documents.application.use_cases.bulk_provision_drive_folders import (
    BulkProvisionDriveFoldersUseCase,
)


def _use_case(*, repository=None, storage=None):
    repository = repository or FakeDocumentRepository()
    storage = storage or FakeDocumentStorage()
    return BulkProvisionDriveFoldersUseCase(repository, storage), repository, storage


@pytest.mark.asyncio
async def test_creates_folders_only_for_active_users_without_one():
    repository = FakeDocumentRepository(
        active_users=[
            ("user-1", "ana.garcia@ameliahub.com"),
            ("user-2", "bruno.diaz@ameliahub.com"),
        ]
    )
    # user-2 ya tiene carpeta cacheada de antes (p. ej. subida manual previa).
    await repository.save_drive_folder_id("user-2", "already-cached-folder")
    use_case, repository, storage = _use_case(repository=repository)

    result = await use_case.execute()

    assert result.created == 1
    assert result.skipped == 1
    assert result.failed == 0
    assert await repository.find_drive_folder_id("user-1") is not None
    assert await repository.find_drive_folder_id("user-2") == "already-cached-folder"


@pytest.mark.asyncio
async def test_is_idempotent_a_second_run_only_skips():
    """Re-ejecutar el batch (retry) no debe volver a crear carpetas ya
    resueltas en la corrida anterior."""
    repository = FakeDocumentRepository(
        active_users=[("user-1", "ana.garcia@ameliahub.com")]
    )
    use_case, repository, storage = _use_case(repository=repository)

    first = await use_case.execute()
    second = await use_case.execute()

    assert first.created == 1
    assert second.created == 0
    assert second.skipped == 1


@pytest.mark.asyncio
async def test_one_employee_failure_does_not_abort_the_rest_and_is_reported():
    """Best-effort por empleado (mismo criterio que `SyncDocumentsUseCase`):
    un fallo puntual de Drive para un empleado no debe frenar el resto del
    batch — se cuenta como fallido y se sigue."""

    class _BrokenStorage(FakeDocumentStorage):
        async def get_or_create_employee_folder(self, email: str) -> str:
            if email == "broken@ameliahub.com":
                raise RuntimeError("Drive no responde.")
            return await super().get_or_create_employee_folder(email)

    repository = FakeDocumentRepository(
        active_users=[
            ("user-broken", "broken@ameliahub.com"),
            ("user-ok", "ok@ameliahub.com"),
        ]
    )
    use_case, repository, storage = _use_case(repository=repository, storage=_BrokenStorage())

    result = await use_case.execute()

    assert result.created == 1  # user-ok
    assert result.failed == 1  # user-broken
    assert result.sync_run.status == "partial"
    assert await repository.find_drive_folder_id("user-ok") is not None
    assert await repository.find_drive_folder_id("user-broken") is None


@pytest.mark.asyncio
async def test_records_a_sync_run_with_success_status_when_nothing_fails():
    repository = FakeDocumentRepository(
        active_users=[("user-1", "ana.garcia@ameliahub.com")]
    )
    use_case, repository, storage = _use_case(repository=repository)

    result = await use_case.execute()

    assert result.sync_run.id in repository.sync_runs
    assert result.sync_run.finished_at is not None
    assert result.sync_run.status == "success"
    assert result.sync_run.files_synced == 1  # reusa la columna existente para "creadas"


@pytest.mark.asyncio
async def test_records_failed_status_when_every_employee_fails():
    class _AlwaysBrokenStorage(FakeDocumentStorage):
        async def get_or_create_employee_folder(self, email: str) -> str:
            raise RuntimeError("Drive no responde.")

    repository = FakeDocumentRepository(
        active_users=[("user-1", "ana.garcia@ameliahub.com")]
    )
    use_case, repository, storage = _use_case(repository=repository, storage=_AlwaysBrokenStorage())

    result = await use_case.execute()

    assert result.sync_run.status == "failed"
    assert result.failed == 1
    assert result.created == 0
