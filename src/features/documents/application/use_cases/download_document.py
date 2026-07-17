"""
Caso de uso: descargar el binario de un documento.

Alcance RGPD (docs/permisos-roles.md): un empleado o socio solo puede
descargar SUS propios documentos; el administrador puede descargar
cualquiera. Mismo criterio de ownership que `ListDocumentsUseCase`.
"""

from ...domain.ports import IDocumentRepository, IDocumentStorage
from ..errors import DocumentForbiddenError, DocumentNotFoundError
from ..results import DocumentDownload


class DownloadDocumentUseCase:
    def __init__(self, repository: IDocumentRepository, storage: IDocumentStorage):
        self._repository = repository
        self._storage = storage

    async def execute(
        self, *, document_id: str, requester_id: str, requester_role: str
    ) -> DocumentDownload:
        document = await self._repository.find_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError(f"No existe el documento id='{document_id}'.")

        is_admin = requester_role == "administrador"
        if not is_admin and document.user_id != requester_id:
            raise DocumentForbiddenError("No puedes descargar el documento de otro usuario.")

        # `DriveFileNotFoundError` (metadatos presentes en Postgres pero sin
        # archivo real en el proveedor activo) se deja propagar sin envolver
        # — WU-C2 la mapea a 404, igual que `DocumentNotFoundError`.
        content = await self._storage.download(document.drive_file_id)
        return DocumentDownload(document=document, content=content)
