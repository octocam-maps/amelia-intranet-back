"""
Adaptador MOCK de `IDocumentStorage` — el que instancia por defecto la
factoría (`DRIVE_PROVIDER=mock`, ver `../factory.get_document_storage`).
100% en memoria, SIN llamada de red ni credenciales de Google: permite
construir y testear el resto del feature (repositorio, use cases, rutas)
sin depender de la aprobación de Domain-Wide Delegation a nivel de
Workspace (ver `sdd/fase4-nominas-documentos/design`, Open Questions). Es
indistinguible desde los use cases de un proveedor real — el día que
`DRIVE_PROVIDER=google` esté disponible en un entorno, solo cambia qué
clase construye la factory.

El estado se guarda en atributos DE CLASE (no de instancia): cada
dependencia de FastAPI construye una instancia nueva por request (mismo
patrón que los repositorios Postgres del proyecto, p. ej.
`PostgresAbsenceRepository`), así que si el estado viviera en `self` se
perdería entre requests. `MockEmailSender` resuelve esto persistiendo en la
tabla `email_log`; aquí no existe una tabla equivalente para el contenido
binario — crear una está fuera del alcance de esta work-unit (la migración
025 solo añade `users.drive_folder_id`) — así que el estado vive en memoria
del proceso, suficiente para dev/test de un solo proceso.
"""

import hashlib
import uuid
from typing import ClassVar, Optional

from ...domain.models import CATEGORY_FOLDER_NAMES, DriveFileMetadata, UploadedFile
from ...domain.ports import DriveFileNotFoundError

# Mismo literal que usa Drive real (`google_drive_client._FOLDER_MIME_TYPE`)
# para distinguir una carpeta de un archivo — se duplica aquí en vez de
# importarlo porque ese módulo es el único que toca `googleapiclient`
# (docstring de `google_drive_client.py`) y este provider no depende de él.
_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


class MockDocumentStorage:
    # Compartido entre TODAS las instancias del proceso (ver docstring del
    # módulo) — no es un default mutable de instancia, es intencional.
    _folders_by_email: ClassVar[dict[str, str]] = {}
    _files_by_folder: ClassVar[dict[str, dict[str, DriveFileMetadata]]] = {}
    _content_by_file_id: ClassVar[dict[str, bytes]] = {}
    # `employee_folder_id -> {category -> subfolder_id}` — refleja la
    # estructura real de Drive (subcarpeta de categoría DENTRO de la
    # carpeta del empleado, ver `CATEGORY_FOLDER_NAMES`).
    _category_folders: ClassVar[dict[str, dict[str, str]]] = {}

    async def get_or_create_employee_folder(self, email: str) -> str:
        folder_id = self._folders_by_email.get(email)
        if folder_id is None:
            folder_id = f"mock-folder-{uuid.uuid4()}"
            self._folders_by_email[email] = folder_id
            self._files_by_folder[folder_id] = {}
        return folder_id

    async def find_employee_folder(self, email: str) -> Optional[str]:
        return self._folders_by_email.get(email)

    async def get_or_create_category_folder(
        self, employee_folder_id: str, category: str
    ) -> str:
        categories = self._category_folders.setdefault(employee_folder_id, {})
        folder_id = categories.get(category)
        if folder_id is None:
            folder_id = f"mock-folder-{uuid.uuid4()}"
            categories[category] = folder_id
            self._files_by_folder[folder_id] = {}
            # Drive real lista las subcarpetas como una entrada más al
            # listar la carpeta del empleado — se refleja aquí para que el
            # filtro por `mimeType` de carpeta en el sync (fallback de
            # archivos sueltos) sea representativo también contra el mock.
            self._files_by_folder.setdefault(employee_folder_id, {})[folder_id] = (
                DriveFileMetadata(
                    drive_file_id=folder_id,
                    name=CATEGORY_FOLDER_NAMES[category],
                    mime_type=_FOLDER_MIME_TYPE,
                    size_bytes=0,
                    content_hash="",
                )
            )
        return folder_id

    async def find_category_folder(
        self, employee_folder_id: str, category: str
    ) -> Optional[str]:
        return self._category_folders.get(employee_folder_id, {}).get(category)

    async def upload(
        self, *, folder_id: str, filename: str, content: bytes, mime_type: str
    ) -> UploadedFile:
        drive_file_id = f"mock-file-{uuid.uuid4()}"
        # md5, igual que el `md5Checksum` real que devuelve Drive (decisión
        # de diseño: content_hash = lo que calcula el proveedor, no un
        # sha256 propio) — ver `sdd/fase4-nominas-documentos/design`.
        content_hash = hashlib.md5(content).hexdigest()
        self._files_by_folder.setdefault(folder_id, {})[drive_file_id] = DriveFileMetadata(
            drive_file_id=drive_file_id,
            name=filename,
            mime_type=mime_type,
            size_bytes=len(content),
            content_hash=content_hash,
        )
        self._content_by_file_id[drive_file_id] = content
        return UploadedFile(drive_file_id=drive_file_id, content_hash=content_hash)

    async def download(self, drive_file_id: str) -> bytes:
        content = self._content_by_file_id.get(drive_file_id)
        if content is None:
            raise DriveFileNotFoundError(
                f"drive_file_id='{drive_file_id}' no existe en MockDocumentStorage."
            )
        return content

    async def list_folder_files(self, folder_id: str) -> list[DriveFileMetadata]:
        return list(self._files_by_folder.get(folder_id, {}).values())

    @classmethod
    def reset(cls) -> None:
        """Vacía el estado compartido de clase. SOLO para tests — sin esto,
        el estado de un test se filtraría al siguiente (misma clase, mismos
        dicts, ver docstring del módulo)."""
        cls._folders_by_email.clear()
        cls._files_by_folder.clear()
        cls._content_by_file_id.clear()
        cls._category_folders.clear()
