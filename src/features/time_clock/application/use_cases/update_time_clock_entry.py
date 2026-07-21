"""
Caso de uso: editar un tramo existente (corregir horas o cerrar uno abierto).
RBAC: solo el dueño del tramo o el admin.
"""

from datetime import datetime
from typing import Optional

from src.shared.auth.roles import RoleCode

from ...domain.entities import TimeClockEntry
from ...domain.errors import (
    InvalidTimeRangeError,
    TimeClockEntryNotFoundError,
    TimeClockForbiddenError,
    TimeClockOverlapError,
)
from ...domain.ports import ITimeClockRepository


class UpdateTimeClockEntryUseCase:
    def __init__(self, repository: ITimeClockRepository):
        self._repository = repository

    async def execute(
        self,
        *,
        entry_id: str,
        requester_id: str,
        requester_role: str,
        clock_in: datetime,
        clock_out: Optional[datetime],
    ) -> TimeClockEntry:
        entry = await self._repository.find_entry_by_id(entry_id)
        if entry is None:
            raise TimeClockEntryNotFoundError("El tramo de fichaje no existe.")

        if requester_role != RoleCode.ADMINISTRADOR and entry.user_id != requester_id:
            raise TimeClockForbiddenError("No puedes editar el fichaje de otro usuario.")

        if clock_in.date() != entry.work_date:
            raise InvalidTimeRangeError(
                "La hora de entrada debe caer dentro de la fecha del tramo."
            )
        if clock_out is not None:
            if clock_out.date() != entry.work_date:
                raise InvalidTimeRangeError("El tramo no puede cruzar de un día a otro.")
            if clock_out <= clock_in:
                raise InvalidTimeRangeError(
                    "La hora de salida debe ser posterior a la de entrada."
                )

        overlapping = await self._repository.find_overlapping_entry(
            entry.user_id, entry.work_date, clock_in, clock_out, exclude_entry_id=entry.id
        )
        if overlapping is not None:
            raise TimeClockOverlapError(
                "Ese tramo se solapa con otro fichaje ya registrado ese día."
            )

        return await self._repository.update_entry(
            entry.id, clock_in=clock_in, clock_out=clock_out
        )
