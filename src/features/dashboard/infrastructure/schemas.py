"""DTOs de response (Pydantic) del feature `dashboard`."""

from datetime import date
from typing import Literal, Optional

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


# --- `GET /dashboard/admin/metrics` -----------------------------------------


class AdminMetricsKPIsDTO(BaseModel):
    absent_today: int
    pending_approvals: int
    clocked_in_now: int
    punctuality_pct: int


class AdminMetricsTrendsDTO(BaseModel):
    absences: list[int]
    clocked_in: list[int]
    punctuality: list[int]


class AttendanceRadarItemDTO(BaseModel):
    user_id: str
    full_name: str
    avatar_url: Optional[str] = None
    kind: Literal["late_in", "overtime_out", "on_time", "negative_balance"]
    value_minutes: int
    detail: str


class AdminMetricsDTO(BaseModel):
    kpis: AdminMetricsKPIsDTO
    trends: AdminMetricsTrendsDTO
    attendance_radar: list[AttendanceRadarItemDTO]
