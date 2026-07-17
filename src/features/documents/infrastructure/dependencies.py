"""Wiring de FastAPI: construye los casos de uso con sus adaptadores
concretos. `UploadDocumentUseCase` reutiliza `PostgresStaffRepository` del
feature `staff` para validar que `user_id` corresponde a un miembro de la
plantilla — no se duplica ese repositorio aquí."""

from src.features.staff.infrastructure.repositories.staff_repository import (
    PostgresStaffRepository,
)
from src.shared.config import get_settings
from src.shared.database import get_database_pool

from ..application.use_cases.delete_document import DeleteDocumentUseCase
from ..application.use_cases.download_document import DownloadDocumentUseCase
from ..application.use_cases.list_documents import ListDocumentsUseCase
from ..application.use_cases.sync_documents import SyncDocumentsUseCase
from ..application.use_cases.upload_document import UploadDocumentUseCase
from .factory import get_document_storage
from .repositories.document_repository import PostgresDocumentRepository


def _get_repository() -> PostgresDocumentRepository:
    return PostgresDocumentRepository(get_database_pool())


def get_list_documents_use_case() -> ListDocumentsUseCase:
    return ListDocumentsUseCase(_get_repository())


def get_upload_document_use_case() -> UploadDocumentUseCase:
    settings = get_settings()
    return UploadDocumentUseCase(
        _get_repository(),
        get_document_storage(),
        PostgresStaffRepository(get_database_pool()),
        settings.documents_max_upload_mb,
    )


def get_download_document_use_case() -> DownloadDocumentUseCase:
    return DownloadDocumentUseCase(_get_repository(), get_document_storage())


def get_delete_document_use_case() -> DeleteDocumentUseCase:
    return DeleteDocumentUseCase(_get_repository())


def get_sync_documents_use_case() -> SyncDocumentsUseCase:
    settings = get_settings()
    return SyncDocumentsUseCase(
        _get_repository(), get_document_storage(), settings.documents_max_upload_mb
    )
