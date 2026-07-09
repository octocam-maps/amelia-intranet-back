"""Fake en memoria de `IDashboardRepository` — permite testear el caso de
uso sin Postgres."""

from datetime import date
from typing import Optional

from src.features.dashboard.domain.entities import (
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
    ):
        self.vacation_balance = vacation_balance
        self.today_clock_status = today_clock_status or TodayClockStatus(
            has_open_entry=False, worked_minutes_today=0
        )
        self.upcoming_holidays = upcoming_holidays or []
        self.pending_absence_requests = pending_absence_requests or []
        self.employees_clocked_in_now = employees_clocked_in_now

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
