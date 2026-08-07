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
import threading
from typing import Any, Optional

import google_auth_httplib2
import httplib2
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
        self._credentials = credentials
        # `service=` es el seam de test (WU-B): permite inyectar un `Resource`
        # construido sobre `HttpMockSequence` sin tocar credenciales reales
        # ni red. `cache_discovery=False` evita que el SDK intente escribir
        # un caché de discovery en disco (irrelevante en contenedores).
        self._service = service or build(
            "drive", "v3", credentials=credentials, cache_discovery=False
        )
        self._thread_local = threading.local()

    def _http(self) -> Optional[httplib2.Http]:
        """Un `http` POR HILO, porque el de `googleapiclient` NO es seguro
        entre hilos.

        El `Resource` que devuelve `build()` lleva un único `httplib2.Http`
        dentro, y ese objeto mantiene UNA conexión TLS reutilizada. El
        provider envuelve cada llamada en `asyncio.to_thread`, así que en
        cuanto el batch provisiona en paralelo hay varios hilos leyendo y
        escribiendo sobre el mismo socket: los bytes de una respuesta se
        mezclan con los de otra y OpenSSL aborta con
        `SSLError: record layer failure`, o el hilo se queda esperando una
        respuesta que ya se llevó otro y muere por `read operation timed out`.

        Ambos errores se vieron en producción al desplegar el paralelismo, y
        ninguno señala a la causa: parecen problemas de red de Google.

        Devuelve `None` cuando no hay credenciales — es el caso del seam de
        test, donde el `service` inyectado trae su propio `HttpMockSequence`.
        `HttpRequest.execute(http=None)` cae al `http` de la propia petición,
        así que pasar `None` es exactamente no tocar nada.
        """
        if self._credentials is None:
            return None
        http = getattr(self._thread_local, "http", None)
        if http is None:
            http = google_auth_httplib2.AuthorizedHttp(
                self._credentials, http=httplib2.Http()
            )
            self._thread_local.http = http
        return http

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
            .execute(http=self._http())
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
            .execute(http=self._http())
        )
        return created["id"]

    def find_folder_parent_id(self, folder_id: str) -> Optional[str]:
        """Bajo qué carpeta cuelga hoy, según Drive.

        En Drive un fichero puede tener varios padres; en la práctica, en una
        unidad compartida tiene exactamente uno. Se devuelve el primero y no se
        finge otra cosa: quien pregunta solo quiere saber si la carpeta está
        donde debería."""
        current = (
            self._service.files()
            .get(fileId=folder_id, fields="parents", supportsAllDrives=True)
            .execute(http=self._http())
        )
        parents = current.get("parents", [])
        if not parents:
            return None
        # La raíz se normaliza a None, que es lo que significa "raíz" en todo
        # el puerto de almacenamiento. Devolver aquí su id real haría que una
        # carpeta ya colocada en la raíz pareciera fuera de sitio en cada
        # pasada del volcado, y se movería una y otra vez a donde ya está.
        return None if parents[0] == self._root_folder_id else parents[0]

    def move_folder(self, folder_id: str, *, new_parent_id: Optional[str] = None) -> None:
        """Recoloca una carpeta bajo otro padre CONSERVANDO su id.
        `new_parent_id=None` la lleva a la raíz configurada.

        Es la operación que hace segura la reorganización por entidades: en
        Drive, mover no cambia el id, así que el `users.drive_folder_id` que
        el backend tiene cacheado (migración 025) sigue siendo válido y los
        documentos ya subidos no se mueven de sitio. La alternativa —crear la
        carpeta nueva en su sitio— dejaría dos carpetas por persona: la vieja,
        a la que el backend seguiría subiendo, y la nueva, vacía.

        Se leen los padres actuales en vez de asumir uno: en Drive un fichero
        puede tener varios, y `removeParents` con un id que no es padre real
        falla.
        """
        current = (
            self._service.files()
            .get(fileId=folder_id, fields="parents", supportsAllDrives=True)
            .execute(http=self._http())
        )
        previous_parents = ",".join(current.get("parents", []))
        self._service.files().update(
            fileId=folder_id,
            addParents=new_parent_id or self._root_folder_id,
            removeParents=previous_parents,
            fields="id, parents",
            supportsAllDrives=True,
        ).execute(http=self._http())

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
            .execute(http=self._http())
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
        # `MediaIoBaseDownload` no acepta `http=` al descargar: se queda con
        # el de la petición. Se lo cambiamos aquí para que la descarga use
        # también el `http` de ESTE hilo — ver `_http`. Sin esto, dos
        # descargas simultáneas comparten socket con el mismo resultado que
        # tuvo el volcado en paralelo.
        http = self._http()
        if http is not None:
            request.http = http
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
                .execute(http=self._http())
            )
            files.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return files
