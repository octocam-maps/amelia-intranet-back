"""
Adaptador asyncpg del puerto `IDashboardRepository`. SQL crudo de SOLO
LECTURA sobre tablas de otros features — ver la nota de diseño en
`domain/entities.py`. No hay ningún INSERT/UPDATE/DELETE en este archivo.
"""

from datetime import date, datetime, timezone
from typing import Optional

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool

from ...domain.entities import (
    DailyTrendPoint,
    PendingAbsenceRequestSummary,
    TodayClockStatus,
    UpcomingHoliday,
    VacationBalanceSummary,
)
from ...domain.ports import IDashboardRepository

_VACATION_TYPE_CODE = "vacaciones"
_MADRID_TZ = "Europe/Madrid"


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

    # --- `GET /dashboard/admin/metrics` --------------------------------

    async def count_absent_today(
        self, today: date, entity_id: Optional[str], department_id: Optional[str]
    ) -> int:
        count = await self._db.fetchval(
            """
            SELECT COUNT(DISTINCT r.user_id)
            FROM absence_requests r
            JOIN users u ON u.id = r.user_id
            WHERE r.status = 'approved'
              AND $1::date BETWEEN r.start_date AND r.end_date
              AND u.deleted_at IS NULL
              AND ($2::uuid IS NULL OR u.entity_id = $2::uuid)
              AND ($3::uuid IS NULL OR u.department_id = $3::uuid)
            """,
            today,
            entity_id,
            department_id,
        )
        return int(count or 0)

    async def count_pending_absence_approvals(
        self, entity_id: Optional[str], department_id: Optional[str]
    ) -> int:
        count = await self._db.fetchval(
            """
            SELECT COUNT(*)
            FROM absence_requests r
            JOIN users u ON u.id = r.user_id
            WHERE r.status = 'pending'
              AND u.deleted_at IS NULL
              AND ($1::uuid IS NULL OR u.entity_id = $1::uuid)
              AND ($2::uuid IS NULL OR u.department_id = $2::uuid)
            """,
            entity_id,
            department_id,
        )
        return int(count or 0)

    async def count_clocked_in_now_filtered(
        self, today: date, entity_id: Optional[str], department_id: Optional[str]
    ) -> int:
        count = await self._db.fetchval(
            """
            SELECT COUNT(*)
            FROM time_clock_entries t
            JOIN users u ON u.id = t.user_id
            WHERE t.work_date = $1
              AND t.clock_out IS NULL
              AND u.deleted_at IS NULL
              AND ($2::uuid IS NULL OR u.entity_id = $2::uuid)
              AND ($3::uuid IS NULL OR u.department_id = $3::uuid)
            """,
            today,
            entity_id,
            department_id,
        )
        return int(count or 0)

    async def list_daily_trends(
        self,
        from_date: date,
        to_date: date,
        entity_id: Optional[str],
        department_id: Optional[str],
    ) -> list[DailyTrendPoint]:
        # Dos consultas separadas (fichajes / ausencias) en lugar de una sola
        # con dos JOINs: cruzar `time_clock_entries` y `absence_requests` por
        # día en la misma query multiplicaría filas (producto cartesiano por
        # día) y complicaría los COUNT — más simple y legible mezclar en
        # Python sobre la misma serie de días.
        clock_rows = await self._db.fetch(
            f"""
            WITH days AS (
                SELECT generate_series($1::date, $2::date, interval '1 day')::date AS day
            ),
            filtered_entries AS (
                SELECT t.work_date, t.clock_in
                FROM time_clock_entries t
                JOIN users u ON u.id = t.user_id
                WHERE u.deleted_at IS NULL
                  AND ($3::uuid IS NULL OR u.entity_id = $3::uuid)
                  AND ($4::uuid IS NULL OR u.department_id = $4::uuid)
            )
            SELECT
                d.day,
                COUNT(e.work_date) AS total_entries,
                COUNT(e.work_date) FILTER (
                    WHERE (e.clock_in AT TIME ZONE '{_MADRID_TZ}')::time <= TIME '09:00'
                ) AS punctual_entries
            FROM days d
            LEFT JOIN filtered_entries e ON e.work_date = d.day
            GROUP BY d.day
            ORDER BY d.day
            """,
            from_date,
            to_date,
            entity_id,
            department_id,
        )
        absence_rows = await self._db.fetch(
            """
            WITH days AS (
                SELECT generate_series($1::date, $2::date, interval '1 day')::date AS day
            ),
            filtered_absences AS (
                SELECT r.user_id, r.start_date, r.end_date
                FROM absence_requests r
                JOIN users u ON u.id = r.user_id
                WHERE r.status = 'approved'
                  AND u.deleted_at IS NULL
                  AND ($3::uuid IS NULL OR u.entity_id = $3::uuid)
                  AND ($4::uuid IS NULL OR u.department_id = $4::uuid)
            )
            SELECT d.day, COUNT(DISTINCT a.user_id) AS absences
            FROM days d
            LEFT JOIN filtered_absences a ON d.day BETWEEN a.start_date AND a.end_date
            GROUP BY d.day
            ORDER BY d.day
            """,
            from_date,
            to_date,
            entity_id,
            department_id,
        )
        absences_by_day = {row["day"]: int(row["absences"] or 0) for row in absence_rows}
        return [
            DailyTrendPoint(
                day=row["day"],
                absences=absences_by_day.get(row["day"], 0),
                clocked_in=int(row["total_entries"] or 0),
                punctual_entries=int(row["punctual_entries"] or 0),
                total_entries=int(row["total_entries"] or 0),
            )
            for row in clock_rows
        ]
