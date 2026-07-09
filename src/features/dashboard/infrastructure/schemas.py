"""DTOs de response (Pydantic) del feature `dashboard`."""

from datetime import date
from typing import Optional

from pydantic import BaseModel


class VacationBalanceDTO(BaseModel):
    entitled_days: float
    used_days: float
    pending_days: float
    available_days: float


class TodayClockStatusDTO(BaseModel):
    has_open_entry: bool
    worked_minutes_today: int


class UpcomingHolidayDTO(BaseModel):
    day: date
    name: str


class PendingAbsenceRequestDTO(BaseModel):
    id: str
    user_id: str
    user_full_name: str
    absence_type_name: str
    start_date: date
    end_date: date
    days_count: float


class DashboardSummaryDTO(BaseModel):
    vacation_balance: Optional[VacationBalanceDTO] = None
    today_clock_status: TodayClockStatusDTO
    upcoming_holidays: list[UpcomingHolidayDTO]
    # Solo presentes si el rol es administrador — `None` para empleado.
    pending_absence_requests: Optional[list[PendingAbsenceRequestDTO]] = None
    employees_clocked_in_now: Optional[int] = None
