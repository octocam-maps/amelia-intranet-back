"""
Caso de uso: listar documentos (nóminas, contratos, generales u otros).

Alcance RGPD (docs/CLAUDE.md § reglas no negociables): un empleado o socio
SOLO ve sus propios documentos — el alcance se resuelve AQUÍ, no en la UI.
`socio` es igual a `empleado` en todo lo relativo a datos propios
(`024_socio_role.sql`), así que comparte la misma rama. Mismo criterio que
`absences.ListAbsenceRequestsUseCase`.
"""

from typing import Optional

from src.shared.auth.roles import RoleCode

from ...domain.models import DOCUMENT_CATEGORIES, Document
from ...domain.ports import IDocumentRepository
from ..errors import DocumentForbiddenError, InvalidDocumentCategoryError


class ListDocumentsUseCase:
    def __init__(self, repository: IDocumentRepository):
        self._repository = repository

    async def execute(
        self,
        *,
        requester_id: str,
        requester_role: str,
        category: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> list[Document]:
        if category is not None and category not in DOCUMENT_CATEGORIES:
            raise InvalidDocumentCategoryError(f"category='{category}' no es válida.")

        if requester_role == RoleCode.ADMINISTRADOR:
            # Vista de administración: sin `user_id` ve TODA la plantilla;
            # con `user_id` filtra por un empleado concreto (AdminDocumentsPage).
            return await self._repository.list_all(category=category, user_id=user_id)

        # Empleado/socio: `user_id` solo puede ser el suyo — si el frontend
        # (o alguien escribiendo la URL a mano) manda el de otro, se rechaza.
        if user_id is not None and user_id != requester_id:
            raise DocumentForbiddenError("No puedes ver los documentos de otro usuario.")

        return await self._repository.list_for_user(requester_id, category=category)
