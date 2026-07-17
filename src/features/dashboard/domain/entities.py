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
# Proyecciones de solo lectura para las tarjetas KPI del Home del
# administrador. Mismo principio que el resto de este archivo: agregan
# `time_clock_entries`/`absence_requests`, nunca escriben.


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
    `infrastructure` — aquí solo viajan los contadores base. Alimenta el KPI
    `punctuality_pct`, que se deriva de esta misma serie diaria."""

    day: date
    absences: int
    clocked_in: int
    punctual_entries: int
    total_entries: int


@dataclass(frozen=True)
class AdminDashboardMetrics:
    kpis: AdminMetricsKPIs
