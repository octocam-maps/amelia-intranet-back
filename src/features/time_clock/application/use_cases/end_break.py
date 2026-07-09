"""Caso de uso: reanudar (cerrar la pausa en curso) el tramo abierto."""

from datetime import datetime, timezone

from ...domain.entities import TimeClockBreak
from ...domain.errors import TimeClockNoOpenBreakError, TimeClockNoOpenEntryError
from ...domain.ports import ITimeClockRepository


class EndBreakUseCase:
    def __init__(self, repository: ITimeClockRepository):
        self._repository = repository

    async def execute(self, *, user_id: str) -> TimeClockBreak:
        open_entry = await self._repository.find_open_entry_for_user(user_id)
        if open_entry is None:
            raise TimeClockNoOpenEntryError("No tienes ningún fichaje en curso.")

        open_break = await self._repository.find_open_break_for_entry(open_entry.id)
        if open_break is None:
            raise TimeClockNoOpenBreakError("No tienes ninguna pausa en curso.")

        return await self._repository.close_break(open_break.id, datetime.now(timezone.utc))
