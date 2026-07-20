"""Tests de `SyncDocumentsUseCase` — conciliación Drive -> Postgres (WU-D):
crea metadata SOLO para los archivos nuevos, categoriza por convención de
nombre, omite los que superan el límite de tamaño/tipo y registra la
corrida en `drive_sync_runs` (vía `FakeDocumentRepository`)."""

import pytest

from src.features.documents.application.tests.fakes import (
    FakeDocumentRepository,
    FakeDocumentStorage,
)
from src.features.documents.application.use_cases.sync_documents import SyncDocumentsUseCase
from src.features.documents.domain.models import Document
from datetime import datetime, timezone


def _use_case(*, repository=None, storage=None, max_upload_mb=10):
    repository = repository or FakeDocumentRepository()
    storage = storage or FakeDocumentStorage()
    use_case = SyncDocumentsUseCase(repository, storage, max_upload_mb)
    return use_case, repository, storage


async def _place_file_in_drive(
    storage: FakeDocumentStorage, *, email: str, filename: str, content: bytes, mime_type: str = "application/pdf"
) -> str:
    """Simula que RRHH coloca un archivo a mano en la subcarpeta del
    empleado — usa el propio `upload` del fake, que ya calcula `md5`, pero
    con un `folder_id` resuelto vía `get_or_create_employee_folder` (el
    equivalente en el fake a "la carpeta ya existe en Drive")."""
    folder_id = await storage.get_or_create_employee_folder(email)
    uploaded = await storage.upload(
        folder_id=folder_id, filename=filename, content=content, mime_type=mime_type
    )
    return uploaded.drive_file_id


@pytest.mark.asyncio
async def test_sync_creates_metadata_only_for_new_files():
    storage = FakeDocumentStorage()
    await _place_file_in_drive(
        storage, email="ana.garcia@ameliahub.com", filename="NOMINA_2026-07_Ana.pdf", content=b"nomina"
    )
    existing_drive_file_id = await _place_file_in_drive(
        storage, email="ana.garcia@ameliahub.com", filename="CONTRATO_Ana.pdf", content=b"contrato"
    )
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
    # El folder ya está cacheado (equivalente a una subida manual previa) —
    # así el sync no necesita resolverlo vía `find_employee_folder`.
    folder_id = await storage.get_or_create_employee_folder("ana.garcia@ameliahub.com")
    await repository.save_drive_folder_id("user-1", folder_id)

    use_case, repository, storage = _use_case(repository=repository, storage=storage)

    sync_run = await use_case.execute()

    documents = await repository.list_for_user("user-1")
    assert len(documents) == 2  # el existente + el nuevo
    new_document = next(d for d in documents if d.id != "doc-existing")
    assert new_document.category == "payslip"
    assert new_document.period == "2026-07"
    assert new_document.uploaded_by is None
    assert sync_run.files_synced == 1
    assert sync_run.status == "success"


@pytest.mark.asyncio
async def test_sync_deriva_la_categoria_de_la_subcarpeta_no_del_nombre_del_archivo():
    storage = FakeDocumentStorage()
    employee_folder = await storage.get_or_create_employee_folder("ana.garcia@ameliahub.com")
    payslip_folder = await storage.get_or_create_category_folder(employee_folder, "payslip")
    await storage.upload(
        folder_id=payslip_folder,
        filename="cualquier_nombre_sin_convencion.pdf",
        content=b"nomina",
        mime_type="application/pdf",
    )
    repository = FakeDocumentRepository(active_users=[("user-1", "ana.garcia@ameliahub.com")])
    await repository.save_drive_folder_id("user-1", employee_folder)
    use_case, repository, storage = _use_case(repository=repository, storage=storage)

    await use_case.execute()

    documents = await repository.list_for_user("user-1")
    assert len(documents) == 1
    assert documents[0].category == "payslip"


@pytest.mark.asyncio
async def test_sync_extrae_periodo_de_nomina_dentro_de_la_subcarpeta_de_categoria():
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
    use_case, repository, storage = _use_case(repository=repository, storage=storage)

    await use_case.execute()

    documents = await repository.list_for_user("user-1")
    assert documents[0].period == "2026-07"


@pytest.mark.asyncio
async def test_sync_no_encuentra_nada_en_una_categoria_sin_subcarpeta_todavia():
    """Si RRHH solo colocó la subcarpeta `Nóminas` pero no `Contratos`, el
    sync no crea una subcarpeta vacía para `contract` (`find_category_folder`,
    nunca `get_or_create_...`) — simplemente no concilia nada ahí."""
    storage = FakeDocumentStorage()
    employee_folder = await storage.get_or_create_employee_folder("ana.garcia@ameliahub.com")
    await storage.get_or_create_category_folder(employee_folder, "payslip")
    repository = FakeDocumentRepository(active_users=[("user-1", "ana.garcia@ameliahub.com")])
    await repository.save_drive_folder_id("user-1", employee_folder)
    use_case, repository, storage = _use_case(repository=repository, storage=storage)

    await use_case.execute()

    assert await storage.find_category_folder(employee_folder, "contract") is None
    assert await repository.list_for_user("user-1") == []


@pytest.mark.asyncio
async def test_sync_fallback_por_nombre_para_archivo_suelto_sin_subcarpeta():
    """Un archivo colocado a mano SIN subcarpeta de categoría sigue
    categorizándose por la convención de nombre previa — el sync no lo
    ignora."""
    storage = FakeDocumentStorage()
    await _place_file_in_drive(
        storage, email="ana.garcia@ameliahub.com", filename="CONTRATO_Ana.pdf", content=b"contrato"
    )
    repository = FakeDocumentRepository(active_users=[("user-1", "ana.garcia@ameliahub.com")])
    use_case, repository, storage = _use_case(repository=repository, storage=storage)

    await use_case.execute()

    documents = await repository.list_for_user("user-1")
    assert len(documents) == 1
    assert documents[0].category == "contract"


@pytest.mark.asyncio
async def test_sync_no_cuenta_las_subcarpetas_de_categoria_como_archivos_omitidos():
    """Las subcarpetas (`Nóminas`, `Contratos`, ...) aparecen como entradas
    al listar la raíz del empleado (igual que en Drive real) — el sync debe
    excluirlas del fallback en vez de contarlas como "omitidas por tipo"."""
    storage = FakeDocumentStorage()
    employee_folder = await storage.get_or_create_employee_folder("ana.garcia@ameliahub.com")
    await storage.get_or_create_category_folder(employee_folder, "payslip")
    await storage.get_or_create_category_folder(employee_folder, "contract")
    repository = FakeDocumentRepository(active_users=[("user-1", "ana.garcia@ameliahub.com")])
    await repository.save_drive_folder_id("user-1", employee_folder)
    use_case, repository, storage = _use_case(repository=repository, storage=storage)

    sync_run = await use_case.execute()

    assert sync_run.files_synced == 0
    assert sync_run.status == "success"
    assert sync_run.error_detail is None


@pytest.mark.asyncio
async def test_sync_categorizes_general_when_name_does_not_match_convention():
    storage = FakeDocumentStorage()
    await _place_file_in_drive(
        storage, email="ana.garcia@ameliahub.com", filename="Manual bienvenida.pdf", content=b"manual"
    )
    repository = FakeDocumentRepository(active_users=[("user-1", "ana.garcia@ameliahub.com")])
    use_case, repository, storage = _use_case(repository=repository, storage=storage)

    await use_case.execute()

    documents = await repository.list_for_user("user-1")
    assert len(documents) == 1
    assert documents[0].category == "general"
    assert documents[0].period is None


@pytest.mark.asyncio
async def test_sync_skips_file_over_size_limit_without_failing():
    storage = FakeDocumentStorage()
    await _place_file_in_drive(
        storage,
        email="ana.garcia@ameliahub.com",
        filename="NOMINA_2026-07_Ana.pdf",
        content=b"x" * (2 * 1024 * 1024),  # 2 MB
    )
    repository = FakeDocumentRepository(active_users=[("user-1", "ana.garcia@ameliahub.com")])
    use_case, repository, storage = _use_case(repository=repository, storage=storage, max_upload_mb=1)

    sync_run = await use_case.execute()

    assert await repository.list_for_user("user-1") == []
    assert sync_run.files_synced == 0
    assert sync_run.status == "success"
    assert "omitido" in sync_run.error_detail


@pytest.mark.asyncio
async def test_sync_skips_employee_without_drive_folder():
    """RRHH todavía no colocó ninguna carpeta a mano — el sync no crea nada
    ni falla, simplemente no tiene qué conciliar para ese empleado."""
    repository = FakeDocumentRepository(active_users=[("user-1", "ana.garcia@ameliahub.com")])
    use_case, repository, storage = _use_case(repository=repository)

    sync_run = await use_case.execute()

    assert await repository.list_for_user("user-1") == []
    assert sync_run.files_synced == 0
    assert sync_run.status == "success"


@pytest.mark.asyncio
async def test_sync_records_run_start_and_finish():
    repository = FakeDocumentRepository()
    use_case, repository, _ = _use_case(repository=repository)

    sync_run = await use_case.execute()

    assert sync_run.id in repository.sync_runs
    assert sync_run.finished_at is not None
    assert sync_run.status == "success"


@pytest.mark.asyncio
async def test_sync_one_employee_failure_does_not_abort_the_rest():
    """Un empleado cuyo storage falla al listar la carpeta no debe abortar
    la conciliación del resto — mismo criterio best-effort del pedido."""
    storage = FakeDocumentStorage()
    await _place_file_in_drive(
        storage, email="ok@ameliahub.com", filename="NOMINA_2026-07_Ok.pdf", content=b"ok"
    )

    class _BrokenStorage(FakeDocumentStorage):
        async def find_employee_folder(self, email: str):
            if email == "broken@ameliahub.com":
                raise RuntimeError("Drive no responde para esta subcarpeta.")
            return await super().find_employee_folder(email)

    broken_storage = _BrokenStorage()
    broken_storage.folders_by_email = storage.folders_by_email
    broken_storage.files_by_folder = storage.files_by_folder
    broken_storage.content_by_file_id = storage.content_by_file_id

    repository = FakeDocumentRepository(
        active_users=[
            ("user-broken", "broken@ameliahub.com"),
            ("user-ok", "ok@ameliahub.com"),
        ]
    )
    use_case, repository, _ = _use_case(repository=repository, storage=broken_storage)

    sync_run = await use_case.execute()

    assert sync_run.files_synced == 1
    assert sync_run.status == "partial"
    assert "1 empleado" in sync_run.error_detail
    assert len(await repository.list_for_user("user-ok")) == 1
