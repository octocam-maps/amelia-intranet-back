"""Fake en memoria de `IDashboardRepository` — permite testear el caso de
uso sin Postgres."""

from datetime import date
from typing import Optional

from src.features.dashboard.domain.entities import (
    DailyTrendPoint,
    EmployeeAttendanceStats,
    PendingAbsenceRequestSummary,
    TodayClockStatus,
    UpcomingHoliday,
    VacationBalanceSummary,
)


class FakeDashboardRepository:
    def __init__(
        self,
        vacation_balance: Optional[VacationBalanceSummary] = None,
        today_clock_status: Optional[TodayClockStatus] = None,
        upcoming_holidays: Optional[list[UpcomingHoliday]] = None,
        pending_absence_requests: Optional[list[PendingAbsenceRequestSummary]] = None,
        employees_clocked_in_now: int = 0,
        absent_today: int = 0,
        pending_approvals: int = 0,
        clocked_in_now_filtered: int = 0,
        daily_trends: Optional[list[DailyTrendPoint]] = None,
        attendance_stats: Optional[list[EmployeeAttendanceStats]] = None,
    ):
        self.vacation_balance = vacation_balance
        self.today_clock_status = today_clock_status or TodayClockStatus(
            has_open_entry=False, worked_minutes_today=0
        )
        self.upcoming_holidays = upcoming_holidays or []
        self.pending_absence_requests = pending_absence_requests or []
        self.employees_clocked_in_now = employees_clocked_in_now
        self.absent_today = absent_today
        self.pending_approvals = pending_approvals
        self.clocked_in_now_filtered = clocked_in_now_filtered
        self.daily_trends = daily_trends or []
        self.attendance_stats = attendance_stats or []
        # Últimos filtros recibidos por cada método — permite a los tests
        # comprobar que el caso de uso propaga entity_id/department_id.
        self.received_filters: dict[str, tuple[Optional[str], Optional[str]]] = {}

    async def get_vacation_balance(
        self, user_id: str, year: int
    ) -> Optional[VacationBalanceSummary]:
        return self.vacation_balance

    async def get_today_clock_status(self, user_id: str, today: date) -> TodayClockStatus:
        return self.today_clock_status

    async def list_upcoming_holidays(self, from_date: date, limit: int) -> list[UpcomingHoliday]:
        return self.upcoming_holidays[:limit]

    async def list_pending_absence_requests(
        self, limit: int
    ) -> list[PendingAbsenceRequestSummary]:
        return self.pending_absence_requests[:limit]

    async def count_employees_clocked_in_now(self) -> int:
        return self.employees_clocked_in_now

    async def count_absent_today(
        self, today: date, entity_id: Optional[str], department_id: Optional[str]
    ) -> int:
        self.received_filters["count_absent_today"] = (entity_id, department_id)
        return self.absent_today

    async def count_pending_absence_approvals(
        self, entity_id: Optional[str], department_id: Optional[str]
    ) -> int:
        self.received_filters["count_pending_absence_approvals"] = (entity_id, department_id)
        return self.pending_approvals

    async def count_clocked_in_now_filtered(
        self, today: date, entity_id: Optional[str], department_id: Optional[str]
    ) -> int:
        self.received_filters["count_clocked_in_now_filtered"] = (entity_id, department_id)
        return self.clocked_in_now_filtered

    async def list_daily_trends(
        self,
        from_date: date,
        to_date: date,
        entity_id: Optional[str],
        department_id: Optional[str],
    ) -> list[DailyTrendPoint]:
        self.received_filters["list_daily_trends"] = (entity_id, department_id)
        return self.daily_trends

    async def list_attendance_stats(
        self,
        from_date: date,
        to_date: date,
        entity_id: Optional[str],
        department_id: Optional[str],
    ) -> list[EmployeeAttendanceStats]:
        self.received_filters["list_attendance_stats"] = (entity_id, department_id)
        return self.attendance_stats
