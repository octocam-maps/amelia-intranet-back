"""Router de `/documents`: nóminas, contratos y documentos generales. El
binario vive en Google Drive (puerto `IDocumentStorage`), Postgres solo
indexa los metadatos (`sdd/fase4-nominas-documentos/design`). Este WU (C2)
cubre exclusivamente el CRUD manual (listar/subir/descargar/borrar) —
`POST /documents/sync` (conciliación automática con Drive) es WU-D, no vive
aquí."""

from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse

from src.shared.auth.dependencies import require_role

from ..application.errors import DocumentNotFoundError
from ..application.use_cases.delete_document import DeleteDocumentUseCase
from ..application.use_cases.download_document import DownloadDocumentUseCase
from ..application.use_cases.list_documents import ListDocumentsUseCase
from ..application.use_cases.upload_document import UploadDocumentUseCase
from ..domain.ports import DriveFileNotFoundError
from .dependencies import (
    get_delete_document_use_case,
    get_download_document_use_case,
    get_list_documents_use_case,
    get_upload_document_use_case,
)
from .mappers import document_to_dto, documents_to_dto
from .schemas import DocumentDTO, DocumentListDTO


def create_documents_router() -> APIRouter:
    router = APIRouter(prefix="/documents", tags=["documents"])

    # El externo-invitado no tiene "Documentos"/"Nóminas" en la matriz de
    # permisos (docs/permisos-roles.md: ❌) — se rechaza en los 4 endpoints,
    # en el BACKEND, no solo ocultando el ítem del navbar.

    @router.get("", response_model=DocumentListDTO)
    async def list_documents(
        category: Optional[str] = Query(None),
        user_id: Optional[str] = Query(
            None, description="Solo el admin puede consultar los documentos de otro usuario"
        ),
        # `socio` [migración 024] = igual que empleado en todo lo relativo a
        # sus propios documentos — el alcance RGPD (solo lo suyo) se resuelve
        # en `ListDocumentsUseCase`, nunca aquí.
        current_user: dict = Depends(require_role("administrador", "empleado", "socio")),
        use_case: ListDocumentsUseCase = Depends(get_list_documents_use_case),
    ):
        documents = await use_case.execute(
            requester_id=current_user["sub"],
            requester_role=current_user["role"],
            category=category,
            user_id=user_id,
        )
        return documents_to_dto(documents)

    @router.post("", response_model=DocumentDTO, status_code=201)
    async def upload_document(
        user_id: str = Form(...),
        category: str = Form(...),
        title: str = Form(...),
        period: Optional[str] = Form(None),
        file: UploadFile = File(...),
        current_user: dict = Depends(require_role("administrador")),
        use_case: UploadDocumentUseCase = Depends(get_upload_document_use_case),
    ):
        """Exclusivo del admin — sube el binario a Drive (subcarpeta del
        empleado) e indexa los metadatos en Postgres. `content`/`mime_type`
        se validan dentro del caso de uso (categoría, MIME, tamaño)."""
        content = await file.read()
        document = await use_case.execute(
            user_id=user_id,
            uploaded_by=current_user["sub"],
            category=category,
            title=title,
            period=period,
            filename=file.filename or title,
            content=content,
            mime_type=file.content_type or "",
        )
        return document_to_dto(document)

    @router.get("/{document_id}/download")
    async def download_document(
        document_id: str,
        current_user: dict = Depends(require_role("administrador", "empleado", "socio")),
        use_case: DownloadDocumentUseCase = Depends(get_download_document_use_case),
    ):
        """Descarga server-side: el binario pasa por el backend, NUNCA se
        expone la URL/id de Drive al cliente (`sdd/fase4-nominas-documentos/design`)."""
        try:
            download = await use_case.execute(
                document_id=document_id,
                requester_id=current_user["sub"],
                requester_role=current_user["role"],
            )
        except DriveFileNotFoundError:
            # No es un `BaseError` (vive en `domain.ports`, sin depender de
            # `shared.errors`, para que el dominio no conozca la capa HTTP)
            # — se traduce aquí al mismo 404 que `DocumentNotFoundError`.
            raise DocumentNotFoundError(
                f"No existe el documento id='{document_id}'."
            ) from None

        document = download.document
        filename = document.title if document.title.lower().endswith(".pdf") else f"{document.title}.pdf"
        # Los headers HTTP son latin-1/ASCII — `title` lo escribe libremente
        # el admin y puede llevar tildes/ñ (p. ej. "Nómina julio 2026.pdf").
        # `filename` lleva un fallback ASCII y `filename*` (RFC 6266) el
        # nombre real codificado, para que los navegadores modernos lo usen.
        ascii_filename = filename.encode("ascii", errors="ignore").decode("ascii") or "documento.pdf"
        return StreamingResponse(
            iter([download.content]),
            media_type=document.mime_type,
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{ascii_filename}"; '
                    f"filename*=UTF-8''{quote(filename)}"
                )
            },
        )

    @router.delete("/{document_id}", status_code=204)
    async def delete_document(
        document_id: str,
        current_user: dict = Depends(require_role("administrador")),
        use_case: DeleteDocumentUseCase = Depends(get_delete_document_use_case),
    ):
        """Soft-delete SOLO en Postgres — nunca borra el archivo real en
        Drive (Drive lo gestiona RRHH directamente, decisión de diseño)."""
        await use_case.execute(document_id=document_id)

    return router
