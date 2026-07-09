"""Caso de uso: fichar salida en vivo — cierra el tramo abierto del usuario."""

from datetime import datetime, timezone

from ...domain.entities import TimeClockEntry
from ...domain.errors import TimeClockNoOpenEntryError
from ...domain.ports import ITimeClockRepository


class ClockOutUseCase:
    def __init__(self, repository: ITimeClockRepository):
        self._repository = repository

    async def execute(self, *, user_id: str) -> TimeClockEntry:
        open_entry = await self._repository.find_open_entry_for_user(user_id)
        if open_entry is None:
            raise TimeClockNoOpenEntryError("No tienes ningún fichaje en curso.")

        now = datetime.now(timezone.utc)

        # Si el usuario ficha salida con una pausa todavía abierta, se cierra
        # también esa pausa en el mismo instante — no tiene sentido dejar una
        # pausa "colgada" tras terminar la jornada.
        open_break = await self._repository.find_open_break_for_entry(open_entry.id)
        if open_break is not None:
            await self._repository.close_break(open_break.id, now)

        return await self._repository.update_entry(
            open_entry.id, clock_in=open_entry.clock_in, clock_out=now
        )
