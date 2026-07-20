"""Mapeo dominio -> DTO del feature `documents`. `drive_file_id`/`content_hash`
no se exponen al cliente: son detalles del proveedor de almacenamiento
(`sdd/fase4-nominas-documentos/design` — nunca se expone la URL/id de Drive)."""

from ..domain.models import Document, SyncRun
from .schemas import DocumentDTO, DocumentListDTO, SyncRunDTO


def document_to_dto(document: Document) -> DocumentDTO:
    return DocumentDTO(
        id=document.id,
        user_id=document.user_id,
        category=document.category,
        title=document.title,
        period=document.period,
        mime_type=document.mime_type,
        uploaded_by=document.uploaded_by,
        uploaded_at=document.uploaded_at,
        created_at=document.created_at,
    )


def documents_to_dto(documents: list[Document]) -> DocumentListDTO:
    return DocumentListDTO(documents=[document_to_dto(d) for d in documents])


def sync_run_to_dto(sync_run: SyncRun) -> SyncRunDTO:
    return SyncRunDTO(
        id=sync_run.id,
        started_at=sync_run.started_at,
        finished_at=sync_run.finished_at,
        status=sync_run.status,
        files_synced=sync_run.files_synced,
        error_detail=sync_run.error_detail,
    )
