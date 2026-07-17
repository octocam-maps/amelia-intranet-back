"""Entidades de dominio del feature `absences`. Sin dependencias de framework/SQL."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


@dataclass(frozen=True)
class AbsenceType:
    """Catálogo configurable (Fase 5) — ver `010_absence_types_defaults.sql`
    para los 3 tipos sembrados (vacaciones, baja médica, asuntos propios)."""

    id: str
    code: str
    name: str
    is_paid: bool
    affects_balance: bool
    default_entitled_days: float
    color: Optional[str]
    is_active: bool
    # Políticas configurables por el admin (019). Con defaults para no romper
    # construcciones existentes que aún no las pasan.
    requires_approval: bool = True
    requires_justification: bool = False
    max_days_per_year: Optional[int] = None


@dataclass(frozen=True)
class AbsenceBalance:
    """Saldo de un usuario para un tipo de ausencia en un año concreto —
    alimenta el "contador en tiempo real" que pide el frontend."""

    id: str
    user_id: str
    absence_type_id: str
    year: int
    entitled_days: float
    used_days: float
    pending_days: float

    @property
    def available_days(self) -> float:
        return self.entitled_days - self.used_days - self.pending_days


@dataclass(frozen=True)
class AbsenceRequest:
    id: str
    user_id: str
    absence_type_id: str
    start_date: date
    end_date: date
    days_count: float
    reason: Optional[str]
    status: str
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime]
    review_note: Optional[str]
    created_at: datetime
    # Solo lo rellenan `list_pending_requests`/`list_all_requests` (JOIN con
    # `users`) — las vistas de admin (bandeja, gantt de plantilla) lo
    # necesitan para no mostrar "Empleado #XXXX". `None` en el resto de
    # consultas (crear, listar las propias) donde no hace falta.
    user_full_name: Optional[str] = None


@dataclass(frozen=True)
class AbsenceCalendarEntry:
    """Una fila del "Calendario general de la plantilla" — vista de RRHH
    EXCLUSIVA del administrador (LOTE 4), acotada a un rango de fechas (mes
    visible por defecto).

    A diferencia de `AbsenceRequest` (que exige un segundo `SELECT` a
    `absence_types` para resolver nombre/color si el consumidor los
    necesita), esta forma ya viene con el JOIN resuelto — el repositorio
    (`list_calendar_entries`) hace `JOIN users` + `JOIN absence_types` en la
    misma query porque tanto la pantalla como los exports (XLSX/PDF)
    necesitan siempre el nombre real de la persona y el tipo de ausencia, no
    solo los IDs."""

    request_id: str
    user_id: str
    user_full_name: str
    absence_type_id: str
    absence_type_name: str
    absence_type_color: Optional[str]
    start_date: date
    end_date: date
    days_count: float
    status: str
