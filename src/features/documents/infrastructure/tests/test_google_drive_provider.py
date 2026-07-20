"""
Tests de `GoogleDriveDocumentStorage` (provider async). El seam de test es
el parámetro `client=` del constructor: un `_FakeGoogleDriveClient` en
memoria sustituye a `GoogleDriveClient` (que sí toca `googleapiclient`,
cubierto en `test_google_drive_client.py`) — así estos tests solo verifican
la traducción async/dominio (asyncio.to_thread, mapeo a `UploadedFile`/
`DriveFileMetadata`, `HttpError` 404 -> `DriveFileNotFoundError`), sin
duplicar la cobertura de flags de Shared Drive.
"""

import httplib2
import pytest
from googleapiclient.errors import HttpError

from src.features.documents.domain.models import DriveFileMetadata, UploadedFile
from src.features.documents.domain.ports import DriveFileNotFoundError
from src.features.documents.infrastructure.providers.google_drive_provider import (
    GoogleDriveDocumentStorage,
)


class _FakeGoogleDriveClient:
    def __init__(self):
        # Clave = `(parent_id, name)` — `parent_id=None` representa la raíz
        # (carpeta del empleado), igual que el default de
        # `GoogleDriveClient.find_folder_by_name`/`create_folder` reales.
        # `created_folders` solo guarda el `name` (sin `parent_id`): ningún
        # test de este módulo necesita distinguir por padre, solo por
        # nombre, y así los tests existentes de la carpeta del empleado no
        # cambian su aserción.
        self.folders: dict[tuple, str] = {}
        self.created_folders: list[str] = []
        self.raise_404_on_download = False

    def find_folder_by_name(self, name, *, parent_id=None):
        return self.folders.get((parent_id, name))

    def create_folder(self, name, *, parent_id=None):
        folder_id = f"folder-{name}" if parent_id is None else f"folder-{parent_id}-{name}"
        self.folders[(parent_id, name)] = folder_id
        self.created_folders.append(name)
        return folder_id

    def upload_file(self, *, folder_id, filename, content, mime_type):
        return f"file-{filename}", "md5-fake-hash"

    def download_file(self, drive_file_id):
        if self.raise_404_on_download:
            resp = httplib2.Response({"status": "404"})
            raise HttpError(resp, b'{"error": {"message": "not found"}}')
        return b"contenido descargado"

    def list_files_in_folder(self, folder_id):
        return [
            {
                "id": "file-1",
                "name": "NOMINA_2026-06_ana.pdf",
                "mimeType": "application/pdf",
                "size": "2048",
                "md5Checksum": "abc123",
            }
        ]


# --- constructor / fail-fast -------------------------------------------------


def test_constructor_falla_sin_root_folder_id():
    with pytest.raises(ValueError, match="DRIVE_ROOT_FOLDER_ID"):
        GoogleDriveDocumentStorage(
            key_path="",
            key_json='{"type": "service_account"}',
            root_folder_id="",
        )


def test_constructor_falla_sin_credenciales():
    with pytest.raises(ValueError, match="Service Account"):
        GoogleDriveDocumentStorage(
            key_path="",
            key_json="",
            root_folder_id="root-folder-123",
        )


def test_constructor_acepta_client_inyectado_sin_construir_credenciales_reales():
    # Con `client=` inyectado no se toca `build_credentials` en absoluto —
    # confirma que el seam de test evita cualquier necesidad de credenciales
    # o red también al construir el provider, no solo al usarlo.
    storage = GoogleDriveDocumentStorage(
        key_path="",
        key_json='{"type": "service_account"}',
        root_folder_id="root-folder-123",
        client=_FakeGoogleDriveClient(),
    )

    assert storage is not None


# --- get_or_create_employee_folder / find_employee_folder -------------------


async def test_get_or_create_employee_folder_crea_si_no_existe():
    fake_client = _FakeGoogleDriveClient()
    storage = GoogleDriveDocumentStorage(
        key_path="",
        key_json="x",
        root_folder_id="root-folder-123",
        client=fake_client,
    )

    folder_id = await storage.get_or_create_employee_folder("ana.gomez@ameliahub.com")

    assert folder_id == "folder-ana.gomez@ameliahub.com"
    assert fake_client.created_folders == ["ana.gomez@ameliahub.com"]


async def test_get_or_create_employee_folder_es_idempotente():
    fake_client = _FakeGoogleDriveClient()
    storage = GoogleDriveDocumentStorage(
        key_path="",
        key_json="x",
        root_folder_id="root-folder-123",
        client=fake_client,
    )

    first = await storage.get_or_create_employee_folder("ana.gomez@ameliahub.com")
    second = await storage.get_or_create_employee_folder("ana.gomez@ameliahub.com")

    assert first == second
    # Solo se crea UNA vez — la segunda llamada la encuentra con find.
    assert fake_client.created_folders == ["ana.gomez@ameliahub.com"]


async def test_find_employee_folder_devuelve_none_si_no_existe():
    storage = GoogleDriveDocumentStorage(
        key_path="",
        key_json="x",
        root_folder_id="root-folder-123",
        client=_FakeGoogleDriveClient(),
    )

    result = await storage.find_employee_folder("nadie@ameliahub.com")

    assert result is None


# --- get_or_create_category_folder / find_category_folder -------------------


async def test_get_or_create_category_folder_crea_bajo_la_carpeta_del_empleado():
    fake_client = _FakeGoogleDriveClient()
    storage = GoogleDriveDocumentStorage(
        key_path="",
        key_json="x",
        root_folder_id="root-folder-123",
        client=fake_client,
    )

    folder_id = await storage.get_or_create_category_folder("folder-empleado-1", "payslip")

    assert folder_id == "folder-folder-empleado-1-Nóminas"
    assert fake_client.created_folders == ["Nóminas"]


async def test_get_or_create_category_folder_es_idempotente():
    fake_client = _FakeGoogleDriveClient()
    storage = GoogleDriveDocumentStorage(
        key_path="",
        key_json="x",
        root_folder_id="root-folder-123",
        client=fake_client,
    )

    first = await storage.get_or_create_category_folder("folder-empleado-1", "contract")
    second = await storage.get_or_create_category_folder("folder-empleado-1", "contract")

    assert first == second
    # Solo se crea UNA vez — la segunda llamada la encuentra con find.
    assert fake_client.created_folders == ["Contratos"]


async def test_get_or_create_category_folder_distingue_categorias_del_mismo_empleado():
    fake_client = _FakeGoogleDriveClient()
    storage = GoogleDriveDocumentStorage(
        key_path="",
        key_json="x",
        root_folder_id="root-folder-123",
        client=fake_client,
    )

    payslip_folder = await storage.get_or_create_category_folder("folder-empleado-1", "payslip")
    contract_folder = await storage.get_or_create_category_folder("folder-empleado-1", "contract")

    assert payslip_folder != contract_folder


async def test_get_or_create_category_folder_distingue_el_mismo_empleado_de_otro():
    fake_client = _FakeGoogleDriveClient()
    storage = GoogleDriveDocumentStorage(
        key_path="",
        key_json="x",
        root_folder_id="root-folder-123",
        client=fake_client,
    )

    folder_a = await storage.get_or_create_category_folder("folder-empleado-a", "general")
    folder_b = await storage.get_or_create_category_folder("folder-empleado-b", "general")

    assert folder_a != folder_b


async def test_find_category_folder_devuelve_none_si_no_existe():
    storage = GoogleDriveDocumentStorage(
        key_path="",
        key_json="x",
        root_folder_id="root-folder-123",
        client=_FakeGoogleDriveClient(),
    )

    result = await storage.find_category_folder("folder-empleado-1", "other")

    assert result is None


async def test_find_category_folder_encuentra_la_creada_por_get_or_create():
    fake_client = _FakeGoogleDriveClient()
    storage = GoogleDriveDocumentStorage(
        key_path="",
        key_json="x",
        root_folder_id="root-folder-123",
        client=fake_client,
    )
    folder_id = await storage.get_or_create_category_folder("folder-empleado-1", "payslip")

    result = await storage.find_category_folder("folder-empleado-1", "payslip")

    assert result == folder_id


# --- upload / download -------------------------------------------------------


async def test_upload_devuelve_uploaded_file_del_dominio():
    storage = GoogleDriveDocumentStorage(
        key_path="",
        key_json="x",
        root_folder_id="root-folder-123",
        client=_FakeGoogleDriveClient(),
    )

    result = await storage.upload(
        folder_id="folder-abc",
        filename="NOMINA_2026-06_ana.pdf",
        content=b"contenido",
        mime_type="application/pdf",
    )

    assert result == UploadedFile(
        drive_file_id="file-NOMINA_2026-06_ana.pdf", content_hash="md5-fake-hash"
    )


async def test_download_devuelve_bytes():
    storage = GoogleDriveDocumentStorage(
        key_path="",
        key_json="x",
        root_folder_id="root-folder-123",
        client=_FakeGoogleDriveClient(),
    )

    content = await storage.download("file-1")

    assert content == b"contenido descargado"


async def test_download_de_archivo_inexistente_traduce_http_error_404_a_drive_file_not_found():
    fake_client = _FakeGoogleDriveClient()
    fake_client.raise_404_on_download = True
    storage = GoogleDriveDocumentStorage(
        key_path="",
        key_json="x",
        root_folder_id="root-folder-123",
        client=fake_client,
    )

    with pytest.raises(DriveFileNotFoundError):
        await storage.download("no-existe")


# --- list_folder_files --------------------------------------------------------


async def test_list_folder_files_mapea_a_drive_file_metadata_del_dominio():
    storage = GoogleDriveDocumentStorage(
        key_path="",
        key_json="x",
        root_folder_id="root-folder-123",
        client=_FakeGoogleDriveClient(),
    )

    files = await storage.list_folder_files("folder-abc")

    assert files == [
        DriveFileMetadata(
            drive_file_id="file-1",
            name="NOMINA_2026-06_ana.pdf",
            mime_type="application/pdf",
            size_bytes=2048,
            content_hash="abc123",
        )
    ]
