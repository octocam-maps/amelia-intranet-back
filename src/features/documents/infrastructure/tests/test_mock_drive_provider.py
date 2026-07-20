"""
Tests de `MockDocumentStorage`. 100% en memoria — nunca toca red ni DB, así
que no hace falta ningún fake de pool (a diferencia de `MockEmailSender`,
que sí escribe en `email_log`).
"""

import pytest

from src.features.documents.domain.ports import DriveFileNotFoundError
from src.features.documents.infrastructure.providers.mock_drive_provider import (
    MockDocumentStorage,
)


@pytest.fixture(autouse=True)
def _reset_mock_storage():
    """El estado de `MockDocumentStorage` vive en atributos de CLASE (ver
    docstring del módulo) — sin este reset, un test filtraría carpetas/
    archivos al siguiente."""
    MockDocumentStorage.reset()
    yield
    MockDocumentStorage.reset()


async def test_get_or_create_employee_folder_es_idempotente_por_email():
    storage = MockDocumentStorage()

    first = await storage.get_or_create_employee_folder("ana.gomez@ameliahub.com")
    second = await storage.get_or_create_employee_folder("ana.gomez@ameliahub.com")

    assert first == second


async def test_get_or_create_employee_folder_distingue_emails_distintos():
    storage = MockDocumentStorage()

    folder_a = await storage.get_or_create_employee_folder("ana.gomez@ameliahub.com")
    folder_b = await storage.get_or_create_employee_folder("luis.perez@ameliahub.com")

    assert folder_a != folder_b


async def test_find_employee_folder_devuelve_none_si_nunca_se_creo():
    storage = MockDocumentStorage()

    result = await storage.find_employee_folder("nadie@ameliahub.com")

    assert result is None


async def test_find_employee_folder_encuentra_la_creada_por_get_or_create():
    storage = MockDocumentStorage()
    folder_id = await storage.get_or_create_employee_folder("ana.gomez@ameliahub.com")

    result = await storage.find_employee_folder("ana.gomez@ameliahub.com")

    assert result == folder_id


# --- get_or_create_category_folder / find_category_folder -------------------


async def test_get_or_create_category_folder_es_idempotente_por_empleado_y_categoria():
    storage = MockDocumentStorage()
    employee_folder = await storage.get_or_create_employee_folder("ana.gomez@ameliahub.com")

    first = await storage.get_or_create_category_folder(employee_folder, "payslip")
    second = await storage.get_or_create_category_folder(employee_folder, "payslip")

    assert first == second


async def test_get_or_create_category_folder_distingue_categorias_del_mismo_empleado():
    storage = MockDocumentStorage()
    employee_folder = await storage.get_or_create_employee_folder("ana.gomez@ameliahub.com")

    payslip_folder = await storage.get_or_create_category_folder(employee_folder, "payslip")
    contract_folder = await storage.get_or_create_category_folder(employee_folder, "contract")

    assert payslip_folder != contract_folder


async def test_get_or_create_category_folder_distingue_la_misma_categoria_entre_empleados():
    storage = MockDocumentStorage()
    folder_a = await storage.get_or_create_employee_folder("ana.gomez@ameliahub.com")
    folder_b = await storage.get_or_create_employee_folder("luis.perez@ameliahub.com")

    category_a = await storage.get_or_create_category_folder(folder_a, "general")
    category_b = await storage.get_or_create_category_folder(folder_b, "general")

    assert category_a != category_b


async def test_find_category_folder_devuelve_none_si_nunca_se_creo():
    storage = MockDocumentStorage()
    employee_folder = await storage.get_or_create_employee_folder("ana.gomez@ameliahub.com")

    result = await storage.find_category_folder(employee_folder, "other")

    assert result is None


async def test_find_category_folder_encuentra_la_creada_por_get_or_create():
    storage = MockDocumentStorage()
    employee_folder = await storage.get_or_create_employee_folder("ana.gomez@ameliahub.com")
    folder_id = await storage.get_or_create_category_folder(employee_folder, "payslip")

    result = await storage.find_category_folder(employee_folder, "payslip")

    assert result == folder_id


async def test_upload_a_una_subcarpeta_de_categoria_no_aparece_en_la_raiz_del_empleado():
    storage = MockDocumentStorage()
    employee_folder = await storage.get_or_create_employee_folder("ana.gomez@ameliahub.com")
    payslip_folder = await storage.get_or_create_category_folder(employee_folder, "payslip")

    await storage.upload(
        folder_id=payslip_folder,
        filename="NOMINA_2026-07_ana.pdf",
        content=b"contenido",
        mime_type="application/pdf",
    )

    assert {f.name for f in await storage.list_folder_files(payslip_folder)} == {
        "NOMINA_2026-07_ana.pdf"
    }
    # La raíz del empleado solo ve la SUBCARPETA (mimeType de carpeta,
    # igual que Drive real), nunca el archivo que está dentro de ella.
    root_entries = await storage.list_folder_files(employee_folder)
    assert [f.drive_file_id for f in root_entries] == [payslip_folder]
    assert root_entries[0].mime_type == "application/vnd.google-apps.folder"


async def test_upload_devuelve_drive_file_id_y_content_hash_md5():
    storage = MockDocumentStorage()
    folder_id = await storage.get_or_create_employee_folder("ana.gomez@ameliahub.com")
    content = b"contenido de prueba de una nomina"

    uploaded = await storage.upload(
        folder_id=folder_id,
        filename="NOMINA_2026-06_ana.pdf",
        content=content,
        mime_type="application/pdf",
    )

    assert uploaded.drive_file_id
    # md5 de 32 hex chars, igual que el md5Checksum real de Drive.
    assert len(uploaded.content_hash) == 32


async def test_download_devuelve_el_mismo_contenido_subido():
    storage = MockDocumentStorage()
    folder_id = await storage.get_or_create_employee_folder("ana.gomez@ameliahub.com")
    content = b"contenido de prueba"
    uploaded = await storage.upload(
        folder_id=folder_id, filename="doc.pdf", content=content, mime_type="application/pdf"
    )

    downloaded = await storage.download(uploaded.drive_file_id)

    assert downloaded == content


async def test_download_de_id_inexistente_levanta_drive_file_not_found():
    storage = MockDocumentStorage()

    with pytest.raises(DriveFileNotFoundError):
        await storage.download("no-existe")


async def test_list_folder_files_devuelve_vacio_para_carpeta_sin_archivos():
    storage = MockDocumentStorage()
    folder_id = await storage.get_or_create_employee_folder("ana.gomez@ameliahub.com")

    files = await storage.list_folder_files(folder_id)

    assert files == []


async def test_list_folder_files_incluye_todos_los_subidos_a_esa_carpeta():
    storage = MockDocumentStorage()
    folder_id = await storage.get_or_create_employee_folder("ana.gomez@ameliahub.com")
    await storage.upload(
        folder_id=folder_id, filename="a.pdf", content=b"a", mime_type="application/pdf"
    )
    await storage.upload(
        folder_id=folder_id, filename="b.pdf", content=b"b", mime_type="application/pdf"
    )

    files = await storage.list_folder_files(folder_id)

    assert {f.name for f in files} == {"a.pdf", "b.pdf"}


async def test_list_folder_files_no_mezcla_archivos_de_otra_carpeta():
    storage = MockDocumentStorage()
    folder_a = await storage.get_or_create_employee_folder("ana.gomez@ameliahub.com")
    folder_b = await storage.get_or_create_employee_folder("luis.perez@ameliahub.com")
    await storage.upload(
        folder_id=folder_a, filename="a.pdf", content=b"a", mime_type="application/pdf"
    )

    files_b = await storage.list_folder_files(folder_b)

    assert files_b == []
