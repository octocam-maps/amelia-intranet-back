"""
Caso de uso: listar tramos de fichaje en un rango de fechas.

RBAC (docs/permisos-roles.md § Control horario): un empleado solo puede
listar los suyos; el admin puede listar los de un usuario concreto o, si no
especifica `target_user_id`, la vista aumentada de TODA la plantilla.
"""

from datetime import date
from typing import Optional

from ...domain.entities import TimeClockEntry
from ...domain.errors import TimeClockForbiddenError
from ...domain.ports import ITimeClockRepository


class ListTimeClockEntriesUseCase:
    def __init__(self, repository: ITimeClockRepository):
        self._repository = repository

    async def execute(
        self,
        *,
        requester_id: str,
        requester_role: str,
        target_user_id: Optional[str],
        date_from: date,
        date_to: date,
    ) -> list[TimeClockEntry]:
        is_admin = requester_role == "administrador"

        if target_user_id is None:
            if is_admin:
                return await self._repository.list_entries_for_all(
                    date_from=date_from, date_to=date_to
                )
            target_user_id = requester_id
        elif not is_admin and target_user_id != requester_id:
            raise TimeClockForbiddenError("No puedes ver el fichaje de otro usuario.")

        return await self._repository.list_entries_for_user(
            target_user_id, date_from=date_from, date_to=date_to
        )
