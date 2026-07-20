"""
Wrapper síncrono de bajo nivel sobre `googleapiclient` — construcción de
credenciales, resolución/creación de subcarpetas, upload/download/list de
archivos. ÚNICO módulo del feature que importa `googleapiclient`/
`google.oauth2`; el resto (provider async, use cases) solo conoce esta
interfaz a través de `GoogleDriveClient`.

Semántica de Unidad compartida (Shared Drive) — decisión del usuario que
REEMPLAZA el Domain-Wide Delegation del diseño original (ver
`sdd/fase4-nominas-documentos/design` y la reconciliación posterior en
engram, obs. #450): la Service Account accede DIRECTAMENTE a la Shared
Drive (como miembro "Administrador de contenido"), SIN `with_subject` /
impersonación — `build_credentials` nunca pasa `subject=`. TODAS las
llamadas van con `supportsAllDrives=True`; `files().list` además con
`includeItemsFromAllDrives=True`, `corpora='drive'`, `driveId=<root>` — sin
esos flags las llamadas no ven contenido de la unidad compartida (fallan en
silencio con una lista vacía, no con un error).

Cliente 100% síncrono a propósito: el SDK oficial de Google no tiene
variante async. Quien lo envuelve en `asyncio.to_thread` por llamada es el
provider (`google_drive_provider.GoogleDriveDocumentStorage`), nunca este
módulo.
"""

import io
import json
from typing import Any, Optional

from google.oauth2 import service_account
from googleapiclient.discovery import Resource, build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

_SCOPES = ["https://www.googleapis.com/auth/drive"]
_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
# Multipart simple ≤5MB, resumible (`MediaIoBaseUpload(resumable=True)`) por
# encima — decisión de diseño: la mayoría de nóminas/contratos son pequeñas,
# resumible solo aporta valor ante corte de red.
_RESUMABLE_THRESHOLD_BYTES = 5 * 1024 * 1024


def build_credentials(
    *, key_path: str, key_json: str
) -> service_account.Credentials:
    """Construye credenciales de Service Account desde `key_json` (JSON
    inline) o `key_path` (ruta a fichero) — se acepta cualquiera de las dos,
    nunca ambas a la vez con distinto resultado (si viene `key_json` gana
    sobre `key_path`, mismo orden que documenta `Settings`). SIN `subject`:
    ver docstring del módulo."""
    if key_json:
        info: dict[str, Any] = json.loads(key_json)
        return service_account.Credentials.from_service_account_info(
            info, scopes=_SCOPES
        )
    if key_path:
        return service_account.Credentials.from_service_account_file(
            key_path, scopes=_SCOPES
        )
    raise ValueError(
        "Faltan credenciales de Service Account: configura "
        "GOOGLE_SERVICE_ACCOUNT_KEY_PATH o GOOGLE_SERVICE_ACCOUNT_KEY_JSON."
    )


def _escape_query_literal(value: str) -> str:
    """Escapa comillas simples para incrustar `value` en una query de Drive
    (`files.list`, sintaxis propia de Drive, no SQL parametrizado — la API
    no ofrece otra forma de pasar el nombre de archivo/carpeta)."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


class GoogleDriveClient:
    """Wrapper síncrono sobre Drive API v3. Todas sus llamadas bloquean el
    hilo — quien las invoca desde código async DEBE envolverlas en
    `asyncio.to_thread` (responsabilidad del provider, no de esta clase)."""

    def __init__(
        self,
        credentials: Optional[service_account.Credentials],
        *,
        root_folder_id: str,
        service: Optional[Resource] = None,
    ):
        self._root_folder_id = root_folder_id
        # `service=` es el seam de test (WU-B): permite inyectar un `Resource`
        # construido sobre `HttpMockSequence` sin tocar credenciales reales
        # ni red. `cache_discovery=False` evita que el SDK intente escribir
        # un caché de discovery en disco (irrelevante en contenedores).
        self._service = service or build(
            "drive", "v3", credentials=credentials, cache_discovery=False
        )

    def find_folder_by_name(
        self, name: str, *, parent_id: Optional[str] = None
    ) -> Optional[str]:
        """Busca una subcarpeta por nombre exacto bajo `parent_id` (por
        defecto la raíz configurada — así la carpeta del empleado sigue
        buscándose bajo `DRIVE_ROOT_FOLDER_ID` sin cambiar la firma en su
        único call site actual), SIN crearla. Devuelve `None` si no existe.
        `driveId`/`corpora` SIEMPRE apuntan a la raíz: es el id de la Unidad
        compartida, no de la carpeta padre bajo la que se busca."""
        parent = parent_id or self._root_folder_id
        query = (
            f"'{parent}' in parents and "
            f"name = '{_escape_query_literal(name)}' and "
            f"mimeType = '{_FOLDER_MIME_TYPE}' and trashed = false"
        )
        response = (
            self._service.files()
            .list(
                q=query,
                fields="files(id, name)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                corpora="drive",
                driveId=self._root_folder_id,
            )
            .execute()
        )
        files = response.get("files", [])
        return files[0]["id"] if files else None

    def create_folder(self, name: str, *, parent_id: Optional[str] = None) -> str:
        """Crea una subcarpeta bajo `parent_id` (por defecto la raíz
        configurada). NO comprueba duplicados — quien llama
        (`GoogleDriveDocumentStorage.get_or_create_employee_folder` /
        `get_or_create_category_folder`) ya resolvió que no existe antes de
        crear."""
        metadata = {
            "name": name,
            "mimeType": _FOLDER_MIME_TYPE,
            "parents": [parent_id or self._root_folder_id],
        }
        created = (
            self._service.files()
            .create(body=metadata, fields="id", supportsAllDrives=True)
            .execute()
        )
        return created["id"]

    def upload_file(
        self, *, folder_id: str, filename: str, content: bytes, mime_type: str
    ) -> tuple[str, str]:
        """Sube `content` a `folder_id`. Devuelve `(drive_file_id,
        md5Checksum)`. Multipart simple si `content` cabe en el umbral,
        resumible si lo supera (ver `_RESUMABLE_THRESHOLD_BYTES`)."""
        resumable = len(content) > _RESUMABLE_THRESHOLD_BYTES
        media = MediaIoBaseUpload(
            io.BytesIO(content), mimetype=mime_type, resumable=resumable
        )
        metadata = {"name": filename, "parents": [folder_id]}
        created = (
            self._service.files()
            .create(
                body=metadata,
                media_body=media,
                fields="id, md5Checksum",
                supportsAllDrives=True,
            )
            .execute()
        )
        return created["id"], created.get("md5Checksum", "")

    def download_file(self, drive_file_id: str) -> bytes:
        """Descarga el archivo COMPLETO a memoria. Levanta
        `googleapiclient.errors.HttpError` (incluido 404) si algo falla —
        la traducción a `DriveFileNotFoundError` del dominio ocurre en el
        provider, no aquí (este módulo no conoce el dominio)."""
        request = self._service.files().get_media(
            fileId=drive_file_id, supportsAllDrives=True
        )
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue()

    def list_files_in_folder(self, folder_id: str) -> list[dict[str, Any]]:
        """Lista TODOS los archivos de `folder_id`, sin filtrar por
        mimeType/tamaño (ese filtro de negocio vive en el use case de sync,
        no aquí). Pagina hasta agotar `nextPageToken`."""
        query = f"'{folder_id}' in parents and trashed = false"
        files: list[dict[str, Any]] = []
        page_token: Optional[str] = None
        while True:
            response = (
                self._service.files()
                .list(
                    q=query,
                    fields="nextPageToken, files(id, name, mimeType, size, md5Checksum)",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    corpora="drive",
                    driveId=self._root_folder_id,
                    pageToken=page_token,
                )
                .execute()
            )
            files.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return files
