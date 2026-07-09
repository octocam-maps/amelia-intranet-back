"""
Adaptador asyncpg del puerto `IDashboardRepository`. SQL crudo de SOLO
LECTURA sobre tablas de otros features — ver la nota de diseño en
`domain/entities.py`. No hay ningún INSERT/UPDATE/DELETE en este archivo.
"""

from datetime import date, datetime, timezone
from typing import Optional

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool

from ...domain.entities import (
    PendingAbsenceRequestSummary,
    TodayClockStatus,
    UpcomingHoliday,
    VacationBalanceSummary,
)
from ...domain.ports import IDashboardRepository

_VACATION_TYPE_CODE = "vacaciones"


class PostgresDashboardRepository(IDashboardRepository):
    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    async def get_vacation_balance(
        self, user_id: str, year: int
    ) -> Optional[VacationBalanceSummary]:
        row = await self._db.fetchrow(
            """
            SELECT b.entitled_days, b.used_days, b.pending_days
            FROM absence_balances b
            JOIN absence_types t ON t.id = b.absence_type_id
            WHERE b.user_id = $1 AND b.year = $2 AND t.code = $3
            """,
            user_id,
            year,
            _VACATION_TYPE_CODE,
        )
        if row is None:
            return None
        return VacationBalanceSummary(
            entitled_days=float(row["entitled_days"]),
            used_days=float(row["used_days"]),
            pending_days=float(row["pending_days"]),
        )

    async def get_today_clock_status(self, user_id: str, today: date) -> TodayClockStatus:
        rows = await self._db.fetch(
            """
            SELECT clock_in, clock_out FROM time_clock_entries
            WHERE user_id = $1 AND work_date = $2
            """,
            user_id,
            today,
        )
        has_open_entry = any(row["clock_out"] is None for row in rows)
        now = datetime.now(timezone.utc)
        worked_minutes = sum(
            int(((row["clock_out"] or now) - row["clock_in"]).total_seconds() // 60) for row in rows
        )
        return TodayClockStatus(has_open_entry=has_open_entry, worked_minutes_today=worked_minutes)

    async def list_upcoming_holidays(self, from_date: date, limit: int) -> list[UpcomingHoliday]:
        rows = await self._db.fetch(
            "SELECT day, name FROM holidays WHERE day >= $1 ORDER BY day ASC LIMIT $2",
            from_date,
            limit,
        )
        return [UpcomingHoliday(day=row["day"], name=row["name"]) for row in rows]

    async def list_pending_absence_requests(
        self, limit: int
    ) -> list[PendingAbsenceRequestSummary]:
        rows = await self._db.fetch(
            """
            SELECT r.id, r.user_id, u.full_name AS user_full_name, t.name AS absence_type_name,
                   r.start_date, r.end_date, r.days_count
            FROM absence_requests r
            JOIN users u ON u.id = r.user_id
            JOIN absence_types t ON t.id = r.absence_type_id
            WHERE r.status = 'pending'
            ORDER BY r.created_at ASC
            LIMIT $1
            """,
            limit,
        )
        return [
            PendingAbsenceRequestSummary(
                id=str(row["id"]),
                user_id=str(row["user_id"]),
                user_full_name=row["user_full_name"],
                absence_type_name=row["absence_type_name"],
                start_date=row["start_date"],
                end_date=row["end_date"],
                days_count=float(row["days_count"]),
            )
            for row in rows
        ]

    async def count_employees_clocked_in_now(self) -> int:
        count = await self._db.fetchval(
            """
            SELECT COUNT(*) FROM time_clock_entries
            WHERE work_date = CURRENT_DATE AND clock_out IS NULL
            """
        )
        return int(count or 0)
