"""
Caso de uso: listar tramos de fichaje en un rango de fechas.

RBAC (docs/permisos-roles.md § Control horario): un empleado solo puede
listar los suyos; el admin puede listar los de un usuario concreto, de VARIOS
a la vez (`target_user_ids`, multi-selector Lote 2) o, si no especifica
ninguno de los dos, la vista aumentada de TODA la plantilla.
"""

from datetime import date
from typing import NamedTuple, Optional

from src.shared.auth.roles import RoleCode

from ...domain.entities import TimeClockEntry
from ...domain.errors import TimeClockForbiddenError
from ...domain.ports import ITimeClockRepository


class TimeClockEntryPage(NamedTuple):
    items: list[TimeClockEntry]
    total: int


class ListTimeClockEntriesUseCase:
    def __init__(self, repository: ITimeClockRepository):
        self._repository = repository

    async def execute(
        self,
        *,
        requester_id: str,
        requester_role: str,
        target_user_id: Optional[str] = None,
        target_user_ids: Optional[list[str]] = None,
        date_from: date,
        date_to: date,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> TimeClockEntryPage:
        is_admin = requester_role == RoleCode.ADMINISTRADOR

        # `target_user_ids` (multi-selector) gana si llega junto con el
        # `target_user_id` singular que sigue vivo por compatibilidad (CSV
        # export, selector single ya en producción). Se deduplica preservando
        # el orden para no golpear la BD dos veces con el mismo id.
        if target_user_ids:
            ids: Optional[list[str]] = list(dict.fromkeys(target_user_ids))
        elif target_user_id is not None:
            ids = [target_user_id]
        else:
            ids = None

        if ids is None:
            if is_admin:
                items = await self._repository.list_entries_for_all(
                    date_from=date_from, date_to=date_to, limit=limit, offset=offset
                )
                total = await self._repository.count_entries_for_all(
                    date_from=date_from, date_to=date_to
                )
                return TimeClockEntryPage(items=items, total=total)
            ids = [requester_id]

        # RGPD: un no-admin solo puede pedir su propio id, y solo UNO —
        # tanto si llega repetido en `target_user_ids` como si es un id ajeno.
        if not is_admin and (len(ids) > 1 or ids[0] != requester_id):
            raise TimeClockForbiddenError("No puedes ver el fichaje de otro usuario.")

        if len(ids) == 1:
            items = await self._repository.list_entries_for_user(
                ids[0], date_from=date_from, date_to=date_to, limit=limit, offset=offset
            )
            total = await self._repository.count_entries_for_user(
                ids[0], date_from=date_from, date_to=date_to
            )
            return TimeClockEntryPage(items=items, total=total)

        items = await self._repository.list_entries_for_users(
            ids, date_from=date_from, date_to=date_to, limit=limit, offset=offset
        )
        total = await self._repository.count_entries_for_users(
            ids, date_from=date_from, date_to=date_to
        )
        return TimeClockEntryPage(items=items, total=total)
