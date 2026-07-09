"""
Caso de uso: listar solicitudes de ausencia. RBAC (docs/permisos-roles.md § Ausencias):
- Empleado: solo las suyas (`mode="own"`, sin `target_user_id`).
- Admin: las de un usuario concreto (`mode="own"` + `target_user_id`), la
  bandeja de pendientes (`mode="pending"`) o el calendario global
  (`mode="all"`).
"""

from typing import Literal, Optional

from ...domain.entities import AbsenceRequest
from ...domain.errors import AbsenceForbiddenError
from ...domain.ports import IAbsenceRepository

Mode = Literal["own", "pending", "all"]


class ListAbsenceRequestsUseCase:
    def __init__(self, repository: IAbsenceRepository):
        self._repository = repository

    async def execute(
        self,
        *,
        requester_id: str,
        requester_role: str,
        mode: Mode = "own",
        target_user_id: Optional[str] = None,
    ) -> list[AbsenceRequest]:
        is_admin = requester_role == "administrador"

        if mode in ("pending", "all") and not is_admin:
            raise AbsenceForbiddenError("Solo el administrador puede ver esta bandeja.")

        if mode == "pending":
            return await self._repository.list_pending_requests()
        if mode == "all":
            return await self._repository.list_all_requests()

        effective_user_id = requester_id
        if target_user_id is not None:
            if not is_admin and target_user_id != requester_id:
                raise AbsenceForbiddenError("No puedes ver las solicitudes de otro usuario.")
            effective_user_id = target_user_id

        return await self._repository.list_requests_for_user(effective_user_id)
