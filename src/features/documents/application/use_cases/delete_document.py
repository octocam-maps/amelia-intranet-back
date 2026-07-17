"""
Caso de uso: el administrador borra (soft-delete) un documento. NUNCA borra
el archivo real en Drive — Drive lo gestiona RRHH directamente
(`sdd/fase4-nominas-documentos/design`, decisión de arquitectura).

No repite el chequeo de rol aquí — el único llamador es
`DELETE /documents/{id}`, protegido con `require_role("administrador")` en
la capa de FastAPI (mismo criterio que `UploadDocumentUseCase`).
"""

from ...domain.ports import IDocumentRepository
from ..errors import DocumentNotFoundError


class DeleteDocumentUseCase:
    def __init__(self, repository: IDocumentRepository):
        self._repository = repository

    async def execute(self, *, document_id: str) -> None:
        deleted = await self._repository.soft_delete(document_id)
        if not deleted:
            raise DocumentNotFoundError(f"No existe el documento id='{document_id}'.")
