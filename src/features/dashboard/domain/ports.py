"""
Puertos (Protocols) del feature `dashboard`. Proyecciones de SOLO LECTURA
sobre tablas de otros features (`time_clock_entries`, `absence_balances`,
`absence_requests`, `holidays`) — ver la nota de diseño en `domain/entities.py`.
`domain` no importa nada de `infrastructure` ni de FastAPI.
"""

from datetime import date
from typing import Optional, Protocol

from .entities import (
    PendingAbsenceRequestSummary,
    TodayClockStatus,
    UpcomingHoliday,
    VacationBalanceSummary,
)


class IDashboardRepository(Protocol):
    async def get_vacation_balance(
        self, user_id: str, year: int
    ) -> Optional[VacationBalanceSummary]:
        """`None` si el usuario todavía no tiene fila de saldo de vacaciones
        para ese año (nunca la ha necesitado — `absences` la crea perezosamente)."""
        ...

    async def get_today_clock_status(self, user_id: str, today: date) -> TodayClockStatus: ...

    async def list_upcoming_holidays(self, from_date: date, limit: int) -> list[UpcomingHoliday]: ...

    async def list_pending_absence_requests(
        self, limit: int
    ) -> list[PendingAbsenceRequestSummary]:
        """Vista aumentada del admin."""
        ...

    async def count_employees_clocked_in_now(self) -> int:
        """Vista aumentada del admin: tramos abiertos hoy (`clock_out IS NULL`)."""
        ...
