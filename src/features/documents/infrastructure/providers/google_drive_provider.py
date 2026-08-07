"""
Adaptador REAL de `IDocumentStorage` sobre Google Drive — se activa con
`DRIVE_PROVIDER=google` (ver `../factory.get_document_storage`). Delega toda
llamada al SDK oficial (síncrono) en `GoogleDriveClient`, envuelta en
`asyncio.to_thread` — decisión de diseño "Cliente Drive síncrono envuelto en
asyncio.to_thread por llamada" (`sdd/fase4-nominas-documentos/design`): el
SDK de Google no tiene variante async, envolver es el patrón mínimo viable.

Modelo de acceso: Unidad compartida (Shared Drive), NO Domain-Wide
Delegation — decisión posterior del usuario (engram #450) que reemplaza el
diseño original. La Service Account entra como miembro "Administrador de
contenido" de la Shared Drive; `GoogleDriveClient`/`build_credentials` nunca
usan `with_subject`. `DRIVE_IMPERSONATE_SUBJECT` (settings de WU-A) queda
SIN USO en este provider — no se lee en ningún punto de este módulo.
"""

import asyncio
from typing import Optional

from googleapiclient.errors import HttpError

from ...domain.models import CATEGORY_FOLDER_NAMES, DriveFileMetadata, UploadedFile
from ...domain.ports import DriveFileNotFoundError
from .google_drive_client import GoogleDriveClient, build_credentials


class GoogleDriveDocumentStorage:
    def __init__(
        self,
        *,
        key_path: str,
        key_json: str,
        root_folder_id: str,
        client: Optional[GoogleDriveClient] = None,
    ):
        # Falla al construir (no al primer upload/download) — mismo patrón
        # que `SendGridEmailSender.__init__`: un DRIVE_PROVIDER=google mal
        # configurado debe abortar en la primera request que resuelve la
        # dependencia, no fallar en silencio a medio uso.
        if not root_folder_id:
            raise ValueError(
                "DRIVE_ROOT_FOLDER_ID está vacío: no se puede usar "
                "DRIVE_PROVIDER=google."
            )
        if not key_path and not key_json:
            raise ValueError(
                "Faltan credenciales de Service Account: configura "
                "GOOGLE_SERVICE_ACCOUNT_KEY_PATH o "
                "GOOGLE_SERVICE_ACCOUNT_KEY_JSON para usar DRIVE_PROVIDER=google."
            )
        self._client = client or GoogleDriveClient(
            build_credentials(key_path=key_path, key_json=key_json),
            root_folder_id=root_folder_id,
        )

    async def get_or_create_entity_folder(self, entity_name: str) -> str:
        """Sin memo ni cerrojo: el id lo guarda `entities.drive_folder_id` [055]
        y quien llama solo llega hasta aquí cuando esa columna está vacía.

        Hubo aquí un caché en memoria con doble comprobación. Resolvía el coste
        —37 personas preguntando por las mismas 4 carpetas— pero no el problema:
        la factoría crea una instancia por petición, así que dos peticiones
        simultáneas tenían dos cachés, ninguna veía a la otra y las dos creaban
        la carpeta. Era estado de la aplicación viviendo en memoria."""
        folder_id = await asyncio.to_thread(self._client.find_folder_by_name, entity_name)
        if folder_id is not None:
            return folder_id
        return await asyncio.to_thread(self._client.create_folder, entity_name)

    async def find_folder_parent_id(self, folder_id: str) -> Optional[str]:
        return await asyncio.to_thread(self._client.find_folder_parent_id, folder_id)

    async def move_folder(self, folder_id: str, *, new_parent_id: Optional[str]) -> None:
        await asyncio.to_thread(
            self._client.move_folder, folder_id, new_parent_id=new_parent_id
        )

    async def get_or_create_employee_folder(
        self, email: str, *, entity_folder_id: Optional[str] = None
    ) -> str:
        """Carpeta del empleado dentro de la de su entidad, que llega YA
        RESUELTA (ver `application/entity_folders.py`).

        `entity_folder_id=None` la deja colgando de la raíz — es el caso del
        externo-invitado, que no pertenece a ninguna sociedad del grupo.

        Los tres casos, en este orden:
          1. Ya está bajo su entidad -> se devuelve tal cual.
          2. Existe SUELTA en la raíz (árbol plano anterior a la
             reorganización) -> se MUEVE, conservando su id.
          3. No existe -> se crea en su sitio.

        El caso 2 es el que impide duplicar: crear una carpeta nueva dejaría
        al backend subiendo a la vieja (tiene su id cacheado en
        `users.drive_folder_id`) y a las personas mirando la nueva, vacía.
        """
        if entity_folder_id is None:
            folder_id = await asyncio.to_thread(self._client.find_folder_by_name, email)
            if folder_id is not None:
                return folder_id
            return await asyncio.to_thread(self._client.create_folder, email)

        existing = await asyncio.to_thread(
            self._client.find_folder_by_name, email, parent_id=entity_folder_id
        )
        if existing is not None:
            return existing

        # Herencia del árbol plano: la carpeta existe pero cuelga de la raíz.
        flat = await asyncio.to_thread(self._client.find_folder_by_name, email)
        if flat is not None:
            await asyncio.to_thread(
                self._client.move_folder, flat, new_parent_id=entity_folder_id
            )
            return flat

        return await asyncio.to_thread(
            self._client.create_folder, email, parent_id=entity_folder_id
        )

    async def find_entity_folder(self, entity_name: str) -> Optional[str]:
        return await asyncio.to_thread(self._client.find_folder_by_name, entity_name)

    async def find_employee_folder(
        self, email: str, *, parent_id: Optional[str] = None
    ) -> Optional[str]:
        return await asyncio.to_thread(
            self._client.find_folder_by_name, email, parent_id=parent_id
        )

    async def get_or_create_category_folder(
        self, employee_folder_id: str, category: str
    ) -> str:
        folder_name = CATEGORY_FOLDER_NAMES[category]
        folder_id = await asyncio.to_thread(
            self._client.find_folder_by_name, folder_name, parent_id=employee_folder_id
        )
        if folder_id is not None:
            return folder_id
        return await asyncio.to_thread(
            self._client.create_folder, folder_name, parent_id=employee_folder_id
        )

    async def find_category_folder(
        self, employee_folder_id: str, category: str
    ) -> Optional[str]:
        folder_name = CATEGORY_FOLDER_NAMES[category]
        return await asyncio.to_thread(
            self._client.find_folder_by_name, folder_name, parent_id=employee_folder_id
        )

    async def upload(
        self, *, folder_id: str, filename: str, content: bytes, mime_type: str
    ) -> UploadedFile:
        drive_file_id, content_hash = await asyncio.to_thread(
            self._client.upload_file,
            folder_id=folder_id,
            filename=filename,
            content=content,
            mime_type=mime_type,
        )
        return UploadedFile(drive_file_id=drive_file_id, content_hash=content_hash)

    async def download(self, drive_file_id: str) -> bytes:
        try:
            return await asyncio.to_thread(self._client.download_file, drive_file_id)
        except HttpError as exc:
            if exc.resp.status == 404:
                raise DriveFileNotFoundError(
                    f"drive_file_id='{drive_file_id}' no existe en Google Drive."
                ) from exc
            raise

    async def list_folder_files(self, folder_id: str) -> list[DriveFileMetadata]:
        raw_files = await asyncio.to_thread(
            self._client.list_files_in_folder, folder_id
        )
        return [
            DriveFileMetadata(
                drive_file_id=raw["id"],
                name=raw["name"],
                mime_type=raw["mimeType"],
                size_bytes=int(raw.get("size", 0)),
                content_hash=raw.get("md5Checksum", ""),
            )
            for raw in raw_files
        ]
