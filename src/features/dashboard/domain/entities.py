"""
Entidades de dominio del feature `dashboard`. Son proyecciones de SOLO
LECTURA que agregan datos de otros features (`time_clock`, `absences`) para
pintar el resumen de Inicio — este feature nunca escribe; crear/editar sigue
siendo responsabilidad exclusiva de cada módulo dueño.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class VacationBalanceSummary:
    entitled_days: float
    used_days: float
    pending_days: float

    @property
    def available_days(self) -> float:
        return self.entitled_days - self.used_days - self.pending_days


@dataclass(frozen=True)
class TodayClockStatus:
    """Estado del fichaje del día para el usuario (puede tener varios tramos)."""

    has_open_entry: bool
    worked_minutes_today: int


@dataclass(frozen=True)
class UpcomingHoliday:
    day: date
    name: str


@dataclass(frozen=True)
class PendingAbsenceRequestSummary:
    """Fila de la bandeja de aprobación — solo la vista del admin."""

    id: str
    user_id: str
    user_full_name: str
    absence_type_name: str
    start_date: date
    end_date: date
    days_count: float


@dataclass(frozen=True)
class EmployeeDashboardSummary:
    """Widgets comunes a cualquier trabajador (docs/permisos-roles.md § Inicio)."""

    vacation_balance: Optional[VacationBalanceSummary]
    today_clock_status: TodayClockStatus
    upcoming_holidays: list[UpcomingHoliday]


@dataclass(frozen=True)
class AdminDashboardSummary(EmployeeDashboardSummary):
    """Vista aumentada (➕) del admin: bandeja de pendientes + vista global."""

    pending_absence_requests: list[PendingAbsenceRequestSummary]
    employees_clocked_in_now: int


# --- `GET /dashboard/admin/metrics` -----------------------------------------
# Proyecciones de solo lectura para las tarjetas KPI + sparklines + radar de
# asistencia del Home del administrador. Mismo principio que el resto de este
# archivo: agregan `time_clock_entries`/`absence_requests`, nunca escriben.


@dataclass(frozen=True)
class AdminMetricsKPIs:
    absent_today: int
    pending_approvals: int
    clocked_in_now: int
    punctuality_pct: int


@dataclass(frozen=True)
class DailyTrendPoint:
    """Punto crudo por día, tal como lo devuelve el repositorio. El cálculo
    de puntualidad (%) es regla de negocio y vive en `application`, nunca en
    `infrastructure` — aquí solo viajan los contadores base."""

    day: date
    absences: int
    clocked_in: int
    punctual_entries: int
    total_entries: int


@dataclass(frozen=True)
class MetricsTrends:
    absences: list[int]
    clocked_in: list[int]
    punctuality: list[int]


@dataclass(frozen=True)
class EmployeeAttendanceStats:
    """Proyección cruda por empleado en el periodo, SOLO sobre tramos de
    fichaje cerrados (`clock_out IS NOT NULL`) — un tramo abierto no tiene
    hora de salida con la que calcular horas extra ni saldo. La
    clasificación en `kind` (radar de asistencia) y los umbrales de
    desviación son regla de negocio → capa de aplicación."""

    user_id: str
    full_name: str
    avatar_url: Optional[str]
    days_clocked: int
    worked_minutes_total: int
    avg_clock_in_minutes: float
    """Promedio de la hora de entrada en minutos desde medianoche, hora de
    Madrid (p.ej. 555.0 = 09:15)."""
    avg_clock_out_minutes: float
    """Idem para la hora de salida."""


@dataclass(frozen=True)
class AttendanceRadarItem:
    user_id: str
    full_name: str
    avatar_url: Optional[str]
    kind: str  # "late_in" | "overtime_out" | "on_time" | "negative_balance"
    value_minutes: int
    detail: str


@dataclass(frozen=True)
class AdminDashboardMetrics:
    kpis: AdminMetricsKPIs
    trends: MetricsTrends
    attendance_radar: list[AttendanceRadarItem]
