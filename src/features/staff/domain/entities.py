"""Entidad de dominio del feature `staff` (gestión de plantilla,
docs/permisos-roles.md § "Gestión de plantilla" — exclusiva del admin).
Sin dependencias de framework/SQL."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


@dataclass(frozen=True)
class StaffMember:
    id: str
    full_name: str
    email: str
    avatar_url: Optional[str]
    job_title: Optional[str]
    department_id: Optional[str]
    department_name: Optional[str]
    entity_id: Optional[str]
    entity_code: Optional[str]
    role_id: str
    role_code: str
    status: str
    hire_date: Optional[date]
    # Entitlement anual de vacaciones vigente (`absence_balances.entitled_days`
    # del tipo `vacaciones` para el año en curso) — `None` si todavía no se
    # le ha creado saldo (p. ej. justo tras el alta, antes del primer login).
    vacation_days_per_year: Optional[float]
    created_at: datetime
