"""Mapeo dominio -> DTO del feature `documents`. `drive_file_id`/`content_hash`
no se exponen al cliente: son detalles del proveedor de almacenamiento
(`sdd/fase4-nominas-documentos/design` — nunca se expone la URL/id de Drive)."""

from ..domain.models import Document
from .schemas import DocumentDTO, DocumentListDTO


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
