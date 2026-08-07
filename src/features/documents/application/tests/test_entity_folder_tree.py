"""
Árbol de Drive por entidades: `RAÍZ / <Entidad> / <email> / <categorías>`.

Lo que se protege aquí es que la reorganización NO duplique carpetas. Una
carpeta de empleado duplicada no da error: deja al backend subiendo a la vieja
—tiene su id cacheado en `users.drive_folder_id`— y a las personas mirando la
nueva, vacía. Nadie se entera hasta que alguien echa en falta una nómina.
"""

from typing import Optional

import pytest

from src.features.documents.application.use_cases.bulk_provision_drive_folders import (
    BulkProvisionDriveFoldersUseCase,
)
from src.features.documents.application.use_cases.provision_employee_drive_folder import (
    ProvisionEmployeeDriveFolderUseCase,
)
from src.features.documents.domain.models import CATEGORY_FOLDER_NAMES

from .fakes import FakeDocumentRepository, FakeDocumentStorage


@pytest.mark.asyncio
async def test_the_employee_folder_hangs_from_their_entity():
    repository = FakeDocumentRepository(entity_name_by_user={"user-1": "Amelia Hub"})
    storage = FakeDocumentStorage()
    use_case = ProvisionEmployeeDriveFolderUseCase(repository, storage)

    await use_case.execute(user_id="user-1", email="ana@ameliahub.com")

    assert storage.entity_by_email["ana@ameliahub.com"] == "Amelia Hub"
    assert "Amelia Hub" in storage.entity_folders


@pytest.mark.asyncio
async def test_the_five_category_subfolders_are_precreated():
    """Antes eran lazy y la carpeta de alguien recién dado de alta se veía
    vacía, indistinguible de un provisioning que falló."""
    repository = FakeDocumentRepository(entity_name_by_user={"user-1": "Amelia Hub"})
    storage = FakeDocumentStorage()
    use_case = ProvisionEmployeeDriveFolderUseCase(repository, storage)

    result = await use_case.execute(user_id="user-1", email="ana@ameliahub.com")

    created = storage.category_folders.get(result.drive_folder_id, {})
    assert set(created) == set(CATEGORY_FOLDER_NAMES)


@pytest.mark.asyncio
async def test_someone_without_an_entity_still_gets_a_folder():
    """El externo-invitado no pertenece a ninguna sociedad: su carpeta cuelga
    de la raíz. Sin este caso, un `JOIN` en vez de `LEFT JOIN` lo dejaría sin
    carpeta y sin error."""
    repository = FakeDocumentRepository()  # sin entidad para nadie
    storage = FakeDocumentStorage()
    use_case = ProvisionEmployeeDriveFolderUseCase(repository, storage)

    result = await use_case.execute(user_id="externo-1", email="externo@gmail.com")

    assert result.created is True
    assert "externo@gmail.com" not in storage.entity_by_email


@pytest.mark.asyncio
async def test_a_precreation_failure_does_not_lose_the_employee_folder():
    """Best-effort en las subcarpetas: si Drive falla en una, la carpeta del
    empleado ya está creada y registrada, que es lo que importa. El primer
    upload de esa categoría la crearía igualmente."""

    class _BrokenCategories(FakeDocumentStorage):
        async def get_or_create_category_folder(self, employee_folder_id: str, category: str) -> str:
            raise RuntimeError("Drive no responde.")

    repository = FakeDocumentRepository(entity_name_by_user={"user-1": "Amelia Hub"})
    use_case = ProvisionEmployeeDriveFolderUseCase(repository, _BrokenCategories())

    result = await use_case.execute(user_id="user-1", email="ana@ameliahub.com")

    assert result.created is True
    assert repository.drive_folder_ids["user-1"] == result.drive_folder_id


@pytest.mark.asyncio
async def test_the_batch_uses_the_entity_it_already_queried():
    """`entity_name` viaja en la misma consulta que los emails. Si el batch lo
    ignorara y lo resolviera por persona, serían N consultas de más para un
    dato que el repositorio ya tenía delante."""
    repository = FakeDocumentRepository(
        active_users=[
            ("user-1", "ana@ameliahub.com", "Amelia Hub"),
            ("user-2", "luis@amelialab.com", "Amelia Lab"),
        ]
    )
    storage = FakeDocumentStorage()

    result = await BulkProvisionDriveFoldersUseCase(repository, storage).execute()

    assert result.created == 2
    assert storage.entity_by_email["ana@ameliahub.com"] == "Amelia Hub"
    assert storage.entity_by_email["luis@amelialab.com"] == "Amelia Lab"


@pytest.mark.asyncio
async def test_an_already_provisioned_employee_is_not_touched_again():
    """Idempotencia: el batch es también el mecanismo de reintento, así que se
    ejecuta más de una vez sobre la misma gente."""
    repository = FakeDocumentRepository(
        active_users=[("user-1", "ana@ameliahub.com", "Amelia Hub")]
    )
    storage = FakeDocumentStorage()
    use_case = BulkProvisionDriveFoldersUseCase(repository, storage)

    first = await use_case.execute()
    second = await use_case.execute()

    assert first.created == 1
    assert second.created == 0
    assert second.skipped == 1


# --- Pasada EN SECO ---------------------------------------------------------


class _ReadOnlySpy(FakeDocumentStorage):
    """Falla si alguien intenta ESCRIBIR. Es la única forma de garantizar que
    la pasada en seco es realmente en seco: comprobar el resultado no bastaría,
    porque un plan correcto puede haber creado carpetas por el camino."""

    async def get_or_create_entity_folder(self, entity_name: str) -> str:
        raise AssertionError("la pasada en seco NO debe crear carpetas de entidad")

    async def get_or_create_employee_folder(self, email, *, entity_name=None) -> str:
        raise AssertionError("la pasada en seco NO debe crear carpetas de empleado")

    async def get_or_create_category_folder(self, employee_folder_id, category) -> str:
        raise AssertionError("la pasada en seco NO debe crear subcarpetas")


@pytest.mark.asyncio
async def test_the_dry_run_never_writes_to_drive():
    repository = FakeDocumentRepository(
        active_users=[("user-1", "ana@ameliahub.com", "Amelia Hub")]
    )

    plan = await BulkProvisionDriveFoldersUseCase(repository, _ReadOnlySpy()).plan()

    assert plan.to_create == 1


@pytest.mark.asyncio
async def test_the_dry_run_leaves_no_sync_run_row():
    """No es auditoría: es una consulta. Dejar traza en `drive_sync_runs`
    ensuciaría el historial de ejecuciones reales."""
    repository = FakeDocumentRepository(
        active_users=[("user-1", "ana@ameliahub.com", "Amelia Hub")]
    )

    await BulkProvisionDriveFoldersUseCase(repository, _ReadOnlySpy()).plan()

    # El fake los indexa por id; vacío es vacío en cualquiera de las dos formas.
    assert not repository.sync_runs


@pytest.mark.asyncio
async def test_the_plan_distinguishes_create_move_and_already_ok():
    repository = FakeDocumentRepository(
        active_users=[
            ("user-nueva", "nueva@ameliahub.com", "Amelia Hub"),
            ("user-plana", "plana@ameliahub.com", "Amelia Hub"),
            ("user-cacheada", "cacheada@ameliahub.com", "Amelia Hub"),
        ]
    )
    storage = FakeDocumentStorage()
    # `plana` ya tiene carpeta suelta en la raíz (árbol heredado).
    await storage.get_or_create_employee_folder("plana@ameliahub.com")
    # `cacheada` ya está registrada en BD.
    repository.drive_folder_ids["user-cacheada"] = "folder-ya-registrada"

    plan = await BulkProvisionDriveFoldersUseCase(repository, storage).plan()

    por_email = {e.email: e.action for e in plan.entries}
    assert por_email["nueva@ameliahub.com"] == "crear"
    assert por_email["plana@ameliahub.com"] == "mover"
    assert por_email["cacheada@ameliahub.com"] == "ya_registrada"


@pytest.mark.asyncio
async def test_the_plan_counts_the_drive_writes_it_would_cost():
    """El número que decide si lanzarlo de una vez: 1 entidad + 2 carpetas de
    empleado + 5 subcarpetas cada una = 13."""
    repository = FakeDocumentRepository(
        active_users=[
            ("user-1", "ana@ameliahub.com", "Amelia Hub"),
            ("user-2", "luis@ameliahub.com", "Amelia Hub"),
        ]
    )

    plan = await BulkProvisionDriveFoldersUseCase(repository, _ReadOnlySpy()).plan()

    assert plan.entity_folders_to_create == ["Amelia Hub"]
    assert plan.category_folders_to_create == 10
    assert plan.estimated_drive_writes == 13


@pytest.mark.asyncio
async def test_the_entity_folder_is_only_counted_once_for_the_whole_company():
    """Contarla por empleado multiplicaría por 40 lo que son 4 carpetas."""
    repository = FakeDocumentRepository(
        active_users=[
            ("u1", "a@ameliahub.com", "Amelia Hub"),
            ("u2", "b@ameliahub.com", "Amelia Hub"),
            ("u3", "c@amelialab.com", "Amelia Lab"),
        ]
    )

    plan = await BulkProvisionDriveFoldersUseCase(repository, _ReadOnlySpy()).plan()

    assert sorted(plan.entity_folders_to_create) == ["Amelia Hub", "Amelia Lab"]
