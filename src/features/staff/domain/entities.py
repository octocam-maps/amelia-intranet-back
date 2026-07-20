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
    # Entitlement anual de vacaciones EFECTIVO y vigente — fuente única de
    # verdad: `absence_balances.entitled_days` del tipo `vacaciones` para el
    # año en curso (lo mismo que consumen el dashboard y el saldo de
    # ausencias). `None` si todavía no se le ha creado saldo (solo debería
    # pasar transitoriamente: `create_staff_member`/`update_staff_member`
    # siembran esta fila siempre, calculada o con override).
    vacation_days_per_year: Optional[float]
    created_at: datetime
    # Override manual del admin sobre el entitlement (`users.vacation_days_override`,
    # 027_users_vacation_days_override.sql). `None` = automático (calculado
    # desde `hire_date`) — DISTINTO de `vacation_days_per_year`: este campo
    # es la INTENCIÓN del admin (¿hay override o no?), no el valor efectivo.
    # Con default para no romper fixtures de OTROS features (p. ej.
    # `documents`) que construyen `StaffMember` a mano sin conocer este
    # detalle de `staff`/`absences`.
    vacation_days_override: Optional[float] = None
    # Lo que daría el cálculo automático AHORA MISMO desde `hire_date`, exista
    # o no un override vigente — para que el frontend pueda mostrar "cálculo
    # automático: X días" sin reimplementar la fórmula de negocio
    # (`vacation_entitlement.calculate_vacation_entitlement_days`). Mismo
    # motivo de default que el campo anterior.
    vacation_days_calculated: float = 0.0
