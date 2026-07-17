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
