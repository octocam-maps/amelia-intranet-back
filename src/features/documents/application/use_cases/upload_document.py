"""
Caso de uso: el administrador sube un documento (nómina, contrato, general u
otro) para un empleado concreto. El binario va a Google Drive vía el puerto
`IDocumentStorage`; Postgres solo indexa los metadatos
(`sdd/fase4-nominas-documentos/design`).

No repite el chequeo de rol aquí — el único llamador es `POST /documents`,
protegido con `require_role("administrador")` en la capa de FastAPI (WU-C2,
mismo criterio que `ReviewAbsenceRequestUseCase`: la autorización real vive
en el router, nunca solo en la UI).
"""

from typing import Optional

from src.features.staff.domain.ports import IStaffRepository

from ...domain.models import DOCUMENT_CATEGORIES, Document
from ...domain.ports import IDocumentRepository, IDocumentStorage
from ..errors import (
    DocumentOwnerNotFoundError,
    DocumentTooLargeError,
    InvalidDocumentCategoryError,
    InvalidDocumentMimeTypeError,
)

_ALLOWED_MIME_TYPE = "application/pdf"


class UploadDocumentUseCase:
    def __init__(
        self,
        repository: IDocumentRepository,
        storage: IDocumentStorage,
        staff_repository: IStaffRepository,
        max_upload_mb: int,
    ):
        self._repository = repository
        self._storage = storage
        self._staff_repository = staff_repository
        # `DOCUMENTS_MAX_UPLOAD_MB` llega en MB desde config (WU-C2) — se
        # convierte a bytes una sola vez aquí, no en cada `execute`.
        self._max_upload_bytes = max_upload_mb * 1024 * 1024

    async def execute(
        self,
        *,
        user_id: str,
        uploaded_by: str,
        category: str,
        title: str,
        period: Optional[str],
        filename: str,
        content: bytes,
        mime_type: str,
    ) -> Document:
        if category not in DOCUMENT_CATEGORIES:
            raise InvalidDocumentCategoryError(f"category='{category}' no es válida.")
        if mime_type != _ALLOWED_MIME_TYPE:
            raise InvalidDocumentMimeTypeError(
                f"Solo se admiten documentos '{_ALLOWED_MIME_TYPE}' (recibido '{mime_type}')."
            )
        if len(content) > self._max_upload_bytes:
            raise DocumentTooLargeError(
                f"El archivo supera el límite de {self._max_upload_bytes // (1024 * 1024)} MB."
            )

        staff_member = await self._staff_repository.find_by_id(user_id)
        if staff_member is None:
            raise DocumentOwnerNotFoundError(f"No existe ningún empleado con id='{user_id}'.")

        # La subcarpeta del empleado se cachea en `users.drive_folder_id`
        # (migración 025) para no volver a buscarla/crearla por nombre en
        # cada subida — se resuelve una sola vez por empleado. La subcarpeta
        # de CATEGORÍA (Nóminas/Contratos/General/Otros, decisión posterior
        # del usuario) NO se cachea aparte: es una llamada más al storage,
        # pero el propio provider ya la resuelve por nombre en O(1) llamadas
        # de lista/creación, igual que antes hacía con la carpeta raíz.
        folder_id = await self._repository.find_drive_folder_id(user_id)
        if folder_id is None:
            folder_id = await self._storage.get_or_create_employee_folder(staff_member.email)
            await self._repository.save_drive_folder_id(user_id, folder_id)

        category_folder_id = await self._storage.get_or_create_category_folder(
            folder_id, category
        )

        uploaded = await self._storage.upload(
            folder_id=category_folder_id, filename=filename, content=content, mime_type=mime_type
        )

        return await self._repository.create(
            user_id=user_id,
            category=category,
            title=title,
            period=period,
            drive_file_id=uploaded.drive_file_id,
            mime_type=mime_type,
            content_hash=uploaded.content_hash,
            uploaded_by=uploaded_by,
        )
