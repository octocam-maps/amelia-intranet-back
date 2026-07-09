"""
Puertos (Protocols) del feature `time_clock`. `domain` no importa nada de
`infrastructure` ni de FastAPI — la implementación concreta (asyncpg) vive
en `infrastructure` y se inyecta aquí por duck typing estructural.
"""

from datetime import date, datetime
from typing import Optional, Protocol

from .entities import TimeClockBreak, TimeClockEntry


class ITimeClockRepository(Protocol):
    async def create_entry(
        self,
        *,
        user_id: str,
        work_date: date,
        clock_in: datetime,
        clock_out: Optional[datetime],
        source: str,
    ) -> TimeClockEntry: ...

    async def find_entry_by_id(self, entry_id: str) -> Optional[TimeClockEntry]: ...

    async def list_entries_for_user(
        self, user_id: str, *, date_from: date, date_to: date
    ) -> list[TimeClockEntry]: ...

    async def list_entries_for_all(
        self, *, date_from: date, date_to: date
    ) -> list[TimeClockEntry]:
        """Vista aumentada del admin: fichajes de TODA la plantilla."""
        ...

    async def find_overlapping_entry(
        self,
        user_id: str,
        work_date: date,
        clock_in: datetime,
        clock_out: Optional[datetime],
        *,
        exclude_entry_id: Optional[str] = None,
    ) -> Optional[TimeClockEntry]:
        """`None` si no hay ningún otro tramo del mismo usuario/día que se
        solape con el rango dado. `exclude_entry_id` se usa al editar un
        tramo existente, para no compararlo contra sí mismo."""
        ...

    async def update_entry(
        self, entry_id: str, *, clock_in: datetime, clock_out: Optional[datetime]
    ) -> TimeClockEntry: ...

    async def delete_entry(self, entry_id: str) -> None: ...

    # --- Fichaje en vivo ---

    async def find_open_entry_for_user(self, user_id: str) -> Optional[TimeClockEntry]:
        """El tramo abierto (`clock_out IS NULL`) del usuario, si lo hay —
        independientemente del `work_date` (cubre jornadas que cruzan la
        medianoche de reloj de pared aunque el tramo en sí no cruce de
        `work_date`, ver `_validate_range`)."""
        ...

    async def find_open_break_for_entry(self, entry_id: str) -> Optional[TimeClockBreak]: ...

    async def create_break(self, entry_id: str, break_start: datetime) -> TimeClockBreak: ...

    async def close_break(self, break_id: str, break_end: datetime) -> TimeClockBreak: ...

    async def get_week_worked_seconds(
        self, user_id: str, week_start: date, week_end: date
    ) -> float:
        """Segundos trabajados en el rango (normalmente lunes-domingo de la
        semana en curso), sumando todos los tramos del usuario y restando el
        tiempo de sus pausas — el tramo/pausa abierto cuenta hasta AHORA."""
        ...
