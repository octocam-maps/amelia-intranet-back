"""
Puertos (Protocols) del feature `dashboard`. Proyecciones de SOLO LECTURA
sobre tablas de otros features (`time_clock_entries`, `absence_balances`,
`absence_requests`, `holidays`) — ver la nota de diseño en `domain/entities.py`.
`domain` no importa nada de `infrastructure` ni de FastAPI.
"""

from datetime import date
from typing import Optional, Protocol

from .entities import (
    DailyTrendPoint,
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

    # --- `GET /dashboard/admin/metrics` --------------------------------
    # `entity_id` en `None` significa "sin filtrar" -> `($n::uuid IS NULL OR
    # ...)`. `department_ids` en `None`/vacío también es "sin filtrar" ->
    # `($n::uuid[] IS NULL OR u.department_id = ANY($n::uuid[]))` — el front
    # agrupa los departamentos por NOMBRE y manda TODOS los `department_id`
    # que comparten ese nombre (uno por sede), nunca se resuelve aquí.

    async def count_absent_today(
        self, today: date, entity_id: Optional[str], department_ids: Optional[list[str]]
    ) -> int:
        """Empleados con una ausencia `approved` cuyo rango incluye `today`."""
        ...

    async def count_pending_absence_approvals(
        self, entity_id: Optional[str], department_ids: Optional[list[str]]
    ) -> int: ...

    async def count_clocked_in_now_filtered(
        self, today: date, entity_id: Optional[str], department_ids: Optional[list[str]]
    ) -> int:
        """Como `count_employees_clocked_in_now`, pero acotado por
        entidad/departamento(s) — método propio de `admin/metrics` para no
        alterar el contrato de `/dashboard/summary`."""
        ...

    async def list_daily_trends(
        self,
        from_date: date,
        to_date: date,
        entity_id: Optional[str],
        department_ids: Optional[list[str]],
    ) -> list[DailyTrendPoint]:
        """Un punto por cada día del rango (inclusive), en orden cronológico
        — incluye los días sin fichajes/ausencias con contadores en 0."""
        ...
