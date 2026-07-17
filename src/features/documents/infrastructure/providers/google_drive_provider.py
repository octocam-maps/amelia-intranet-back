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

from ...domain.models import DriveFileMetadata, UploadedFile
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

    async def get_or_create_employee_folder(self, email: str) -> str:
        folder_id = await asyncio.to_thread(self._client.find_folder_by_name, email)
        if folder_id is not None:
            return folder_id
        return await asyncio.to_thread(self._client.create_folder, email)

    async def find_employee_folder(self, email: str) -> Optional[str]:
        return await asyncio.to_thread(self._client.find_folder_by_name, email)

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
