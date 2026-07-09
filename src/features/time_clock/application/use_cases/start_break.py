"""Caso de uso: iniciar una pausa (botón Pausa) dentro del tramo abierto."""

from datetime import datetime, timezone

from ...domain.entities import TimeClockBreak
from ...domain.errors import TimeClockBreakAlreadyOpenError, TimeClockNoOpenEntryError
from ...domain.ports import ITimeClockRepository


class StartBreakUseCase:
    def __init__(self, repository: ITimeClockRepository):
        self._repository = repository

    async def execute(self, *, user_id: str) -> TimeClockBreak:
        open_entry = await self._repository.find_open_entry_for_user(user_id)
        if open_entry is None:
            raise TimeClockNoOpenEntryError("No tienes ningún fichaje en curso para pausar.")

        open_break = await self._repository.find_open_break_for_entry(open_entry.id)
        if open_break is not None:
            raise TimeClockBreakAlreadyOpenError("Ya tienes una pausa en curso.")

        return await self._repository.create_break(open_entry.id, datetime.now(timezone.utc))
