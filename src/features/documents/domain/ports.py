"""
Puertos (Protocols) del feature `documents`. `domain` no importa nada de
`infrastructure` ni de FastAPI — las implementaciones concretas (Postgres
para `IDocumentRepository`, Drive real o mock para `IDocumentStorage`) viven
en `infrastructure` y se inyectan aquí por duck typing estructural, igual
que el resto de puertos del proyecto.
"""

from typing import Optional, Protocol

from .models import Document, DriveFileMetadata, SyncRun, UploadedFile


class DriveFileNotFoundError(Exception):
    """El `drive_file_id` no corresponde a ningún archivo en el proveedor de
    almacenamiento activo. Tanto `MockDocumentStorage` (WU-A) como el
    proveedor real de Google Drive (WU-B) deben levantar esta MISMA clase —
    así el caso de uso que traduce a 404 (WU-C1, `DownloadDocumentUseCase`)
    no necesita distinguir qué `DRIVE_PROVIDER` está activo."""


class IDocumentRepository(Protocol):
    async def find_by_id(self, document_id: str) -> Optional[Document]: ...

    async def list_for_user(
        self, user_id: str, *, category: Optional[str] = None
    ) -> list[Document]:
        """RGPD: SIEMPRE filtrado por `user_id` — nunca expone documentos de
        otro usuario (docs/permisos-roles.md). Excluye `deleted_at`."""
        ...

    async def list_all(
        self, *, category: Optional[str] = None, user_id: Optional[str] = None
    ) -> list[Document]:
        """Vista de administración (sin scoping por dueño). `user_id`
        opcional para que el admin filtre por un empleado concreto."""
        ...

    async def create(
        self,
        *,
        user_id: str,
        category: str,
        title: str,
        period: Optional[str],
        drive_file_id: Optional[str],
        mime_type: str,
        content_hash: Optional[str],
        uploaded_by: Optional[str],
    ) -> Document:
        """`uploaded_by=None` identifica una fila insertada por el sync
        automático (WU-D), no por la subida manual de un admin."""
        ...

    async def soft_delete(self, document_id: str) -> bool:
        """`UPDATE ... SET deleted_at = CURRENT_TIMESTAMP WHERE id = $1 AND
        deleted_at IS NULL` — `True` si borró una fila, `False` si ya estaba
        borrada o no existe. NUNCA borra/mueve el archivo en Drive (decisión
        de diseño: Drive lo gestiona RRHH directamente)."""
        ...

    async def find_drive_folder_id(self, user_id: str) -> Optional[str]:
        """Lee el `users.drive_folder_id` cacheado (migración 025)."""
        ...

    async def save_drive_folder_id(self, user_id: str, drive_folder_id: str) -> None:
        """Cachea el id de la subcarpeta resuelta la primera vez, para no
        volver a buscarla por nombre en cada subida/descarga."""
        ...

    async def find_active_users_with_email(self) -> list[tuple[str, str]]:
        """`(user_id, email)` de empleados con `status='active'` — el sync
        (WU-D) itera solo sobre estos, nunca sobre externos-invitados ni
        usuarios de baja."""
        ...

    async def create_sync_run(self) -> SyncRun:
        """Inserta una fila en `drive_sync_runs` con `status='running'`."""
        ...

    async def finish_sync_run(
        self,
        sync_run_id: str,
        *,
        status: str,
        files_synced: int,
        error_detail: Optional[str],
    ) -> SyncRun: ...


class IDocumentStorage(Protocol):
    """Puerto sobre el proveedor de almacenamiento del BINARIO (Google Drive
    real o `MockDocumentStorage`). Postgres nunca guarda el contenido del
    archivo, solo los metadatos vía `IDocumentRepository`."""

    async def get_or_create_employee_folder(self, email: str) -> str:
        """Devuelve el id de la subcarpeta del empleado (nombre = `email`)
        bajo `DRIVE_ROOT_FOLDER_ID`, CREÁNDOLA si no existe. Lo usa el flujo
        de subida manual (admin, WU-C1) — el admin siempre puede subir aunque
        sea el primer documento de esa persona."""
        ...

    async def find_employee_folder(self, email: str) -> Optional[str]:
        """Busca la subcarpeta por nombre = `email` SIN crearla — la usa el
        sync (WU-D): si RRHH todavía no colocó ninguna carpeta a mano para
        ese empleado, el sync simplemente no encuentra nada que conciliar,
        nunca crea una carpeta vacía."""
        ...

    async def upload(
        self, *, folder_id: str, filename: str, content: bytes, mime_type: str
    ) -> UploadedFile:
        """Sube el archivo a la subcarpeta indicada. La implementación real
        decide multipart simple (≤5MB) vs. resumible (>5MB) — el puerto no
        expone esa distinción, es un detalle del adaptador de Drive."""
        ...

    async def download(self, drive_file_id: str) -> bytes:
        """Descarga el archivo COMPLETO a memoria. Solo se usa con ficheros
        ≤ `DOCUMENTS_MAX_UPLOAD_MB` (validado en el use case, WU-C1).
        Levanta `DriveFileNotFoundError` si `drive_file_id` no existe."""
        ...

    async def list_folder_files(self, folder_id: str) -> list[DriveFileMetadata]:
        """Lista TODOS los archivos de la subcarpeta, sin filtrar — el
        filtro de negocio (mimeType/tamaño) para el sync vive en el use
        case (WU-D), no en este puerto."""
        ...
