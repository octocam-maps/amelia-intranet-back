"""Fakes en memoria de `IDocumentRepository`/`IDocumentStorage` — permiten
testear los casos de uso sin Postgres ni Google Drive, igual que en
`features/absences`. `FakeStaffRepository` es un doble MÍNIMO de
`staff.domain.ports.IStaffRepository`: solo implementa `find_by_id`, lo
único que usa `UploadDocumentUseCase` (es un `Protocol` estructural — no
hace falta implementar el resto de métodos para que el duck typing
funcione).

`find_active_users_with_email`/`create_sync_run`/`finish_sync_run` se
implementaron de verdad en WU-D (`SyncDocumentsUseCase`) — hasta entonces
eran placeholders fuera de alcance de WU-C1."""

import hashlib
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Optional

from src.features.documents.domain.models import (
    CATEGORY_FOLDER_NAMES,
    Document,
    DriveFileMetadata,
    SyncRun,
    UploadedFile,
)
from src.features.documents.domain.ports import DriveFileNotFoundError
from src.features.staff.domain.entities import StaffMember

# Mismo literal que `MockDocumentStorage._FOLDER_MIME_TYPE` — ver su
# docstring: se duplica en vez de compartir un import porque cada adaptador
# de `IDocumentStorage` (real, mock, fake de tests) es independiente.
_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


class FakeDocumentRepository:
    def __init__(
        self,
        documents: Optional[list[Document]] = None,
        *,
        active_users: Optional[list[tuple[str, str, Optional[str]]]] = None,
        invited_users: Optional[list[tuple[str, str, Optional[str]]]] = None,
        entity_name_by_user: Optional[dict[str, str]] = None,
    ):
        self.documents: dict[str, Document] = {d.id: d for d in (documents or [])}
        self.drive_folder_ids: dict[str, str] = {}
        # `(user_id, email)` de empleados activos — consumido por el sync
        # (WU-D, `SyncDocumentsUseCase`). Vacío por defecto para no afectar
        # los tests de WU-C1 que no lo usan.
        # `(user_id, email, entity_name)` — el tercer elemento se admite
        # ausente para no reescribir los tests que no van de entidades.
        self.active_users: list[tuple[str, str, Optional[str]]] = [
            (u if len(u) == 3 else (*u, None)) for u in (active_users or [])
        ]
        # Los `invited` los ve el batch de carpetas y NO el sync — son dos
        # métodos distintos del puerto a propósito. Separarlos aquí es lo que
        # permite que un test note si el batch se equivoca de consulta:
        # con una sola lista, leer el método erróneo daría el mismo resultado.
        self.invited_users: list[tuple[str, str, Optional[str]]] = [
            (u if len(u) == 3 else (*u, None)) for u in (invited_users or [])
        ]
        self.entity_name_by_user: dict[str, str] = entity_name_by_user or {}
        self.sync_runs: dict[str, SyncRun] = {}
        self._sync_run_counter = 0

    async def find_by_id(self, document_id: str) -> Optional[Document]:
        document = self.documents.get(document_id)
        if document is None or document.deleted_at is not None:
            return None
        return document

    async def list_for_user(
        self, user_id: str, *, category: Optional[str] = None
    ) -> list[Document]:
        return [
            d
            for d in self.documents.values()
            if d.user_id == user_id
            and d.deleted_at is None
            and (category is None or d.category == category)
        ]

    async def list_all(
        self, *, category: Optional[str] = None, user_id: Optional[str] = None
    ) -> list[Document]:
        return [
            d
            for d in self.documents.values()
            if d.deleted_at is None
            and (category is None or d.category == category)
            and (user_id is None or d.user_id == user_id)
        ]

    async def create(
        self,
        *,
        user_id,
        category,
        title,
        period,
        drive_file_id,
        mime_type,
        content_hash,
        uploaded_by,
    ) -> Document:
        document_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        document = Document(
            id=document_id,
            user_id=user_id,
            category=category,
            title=title,
            period=period,
            drive_file_id=drive_file_id,
            mime_type=mime_type,
            content_hash=content_hash,
            uploaded_by=uploaded_by,
            uploaded_at=now,
            created_at=now,
            deleted_at=None,
        )
        self.documents[document_id] = document
        return document

    async def soft_delete(self, document_id: str) -> bool:
        document = self.documents.get(document_id)
        if document is None or document.deleted_at is not None:
            return False
        self.documents[document_id] = replace(document, deleted_at=datetime.now(timezone.utc))
        return True

    async def find_drive_folder_id(self, user_id: str) -> Optional[str]:
        return self.drive_folder_ids.get(user_id)

    async def save_drive_folder_id(self, user_id: str, drive_folder_id: str) -> None:
        self.drive_folder_ids[user_id] = drive_folder_id

    async def find_active_users_with_email(self) -> list[tuple[str, str, Optional[str]]]:
        return list(self.active_users)

    async def find_provisionable_users_with_email(
        self,
    ) -> list[tuple[str, str, Optional[str]]]:
        return list(self.active_users) + list(self.invited_users)

    async def find_entity_name_for_user(self, user_id: str) -> Optional[str]:
        return self.entity_name_by_user.get(user_id)

    async def create_sync_run(self) -> SyncRun:
        self._sync_run_counter += 1
        sync_run_id = f"fake-sync-run-{self._sync_run_counter}"
        sync_run = SyncRun(
            id=sync_run_id,
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            status="running",
            files_synced=0,
            error_detail=None,
        )
        self.sync_runs[sync_run_id] = sync_run
        return sync_run

    async def finish_sync_run(self, sync_run_id, *, status, files_synced, error_detail) -> SyncRun:
        updated = replace(
            self.sync_runs[sync_run_id],
            finished_at=datetime.now(timezone.utc),
            status=status,
            files_synced=files_synced,
            error_detail=error_detail,
        )
        self.sync_runs[sync_run_id] = updated
        return updated


class FakeDocumentStorage:
    """Doble de `IDocumentStorage` con estado de INSTANCIA (a diferencia de
    `MockDocumentStorage`, que lo guarda a nivel de clase para sobrevivir
    entre requests reales) — así cada test parte de un estado limpio sin
    necesitar `.reset()`."""

    def __init__(self):
        self.folders_by_email: dict[str, str] = {}
        # Reorganización por entidades: carpeta de cada sociedad y bajo cuál
        # quedó cada persona.
        self.entity_folders: dict[str, str] = {}
        self.entity_by_email: dict[str, str] = {}
        self.files_by_folder: dict[str, dict[str, DriveFileMetadata]] = {}
        self.content_by_file_id: dict[str, bytes] = {}
        self.upload_calls: list[dict] = []  # para aserciones "llamó al storage"
        # `employee_folder_id -> {category -> subfolder_id}`, igual que
        # `MockDocumentStorage._category_folders`.
        self.category_folders: dict[str, dict[str, str]] = {}

    async def get_or_create_entity_folder(self, entity_name: str) -> str:
        folder_id = self.entity_folders.get(entity_name)
        if folder_id is None:
            folder_id = f"fake-entity-{uuid.uuid4()}"
            self.entity_folders[entity_name] = folder_id
        return folder_id

    async def get_or_create_employee_folder(
        self, email: str, *, entity_name: Optional[str] = None
    ) -> str:
        # Mover conserva el id también aquí, igual que en Drive real: la
        # entidad se registra aparte y la carpeta NO cambia de identificador.
        if entity_name is not None:
            await self.get_or_create_entity_folder(entity_name)
            self.entity_by_email[email] = entity_name
        folder_id = self.folders_by_email.get(email)
        if folder_id is None:
            folder_id = f"fake-folder-{uuid.uuid4()}"
            self.folders_by_email[email] = folder_id
            self.files_by_folder[folder_id] = {}
        return folder_id

    async def find_entity_folder(self, entity_name: str) -> Optional[str]:
        return self.entity_folders.get(entity_name)

    async def find_employee_folder(
        self, email: str, *, parent_id: Optional[str] = None
    ) -> Optional[str]:
        return self.folders_by_email.get(email)

    async def get_or_create_category_folder(
        self, employee_folder_id: str, category: str
    ) -> str:
        categories = self.category_folders.setdefault(employee_folder_id, {})
        folder_id = categories.get(category)
        if folder_id is None:
            folder_id = f"fake-folder-{uuid.uuid4()}"
            categories[category] = folder_id
            self.files_by_folder[folder_id] = {}
            # Mismo criterio que `MockDocumentStorage`: la subcarpeta
            # aparece como una entrada más al listar la carpeta del
            # empleado, igual que en Drive real — necesario para que el
            # test del fallback (archivos sueltos, sin subcarpeta) del sync
            # sea representativo.
            self.files_by_folder.setdefault(employee_folder_id, {})[folder_id] = (
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
        return self.category_folders.get(employee_folder_id, {}).get(category)

    async def upload(
        self, *, folder_id: str, filename: str, content: bytes, mime_type: str
    ) -> UploadedFile:
        self.upload_calls.append(
            {
                "folder_id": folder_id,
                "filename": filename,
                "content": content,
                "mime_type": mime_type,
            }
        )
        drive_file_id = f"fake-file-{uuid.uuid4()}"
        content_hash = hashlib.md5(content).hexdigest()
        self.files_by_folder.setdefault(folder_id, {})[drive_file_id] = DriveFileMetadata(
            drive_file_id=drive_file_id,
            name=filename,
            mime_type=mime_type,
            size_bytes=len(content),
            content_hash=content_hash,
        )
        self.content_by_file_id[drive_file_id] = content
        return UploadedFile(drive_file_id=drive_file_id, content_hash=content_hash)

    async def download(self, drive_file_id: str) -> bytes:
        content = self.content_by_file_id.get(drive_file_id)
        if content is None:
            raise DriveFileNotFoundError(f"drive_file_id='{drive_file_id}' no existe.")
        return content

    async def list_folder_files(self, folder_id: str) -> list[DriveFileMetadata]:
        return list(self.files_by_folder.get(folder_id, {}).values())


class FakeStaffRepository:
    def __init__(self, members: Optional[list[StaffMember]] = None):
        self.members: dict[str, StaffMember] = {m.id: m for m in (members or [])}

    async def find_by_id(self, user_id: str) -> Optional[StaffMember]:
        return self.members.get(user_id)
