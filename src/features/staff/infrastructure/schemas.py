"""DTOs de request/response (Pydantic) del feature `staff`."""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field

# `role` NO es un `Literal` fijo: la fuente única de qué roles existen es la
# tabla `roles` (ver `GET /roles`, feature `roles`). `CreateStaffMemberUseCase`/
# `UpdateStaffMemberUseCase` ya resuelven `role_code` contra esa tabla
# (`resolve_role_id`) y devuelven `InvalidRoleCodeError` (422) si no existe —
# duplicar la enumeración aquí como `Literal[...]` obligaba a tocar este
# archivo cada vez que se sumaba un rol (pasó con `socio`, migración 024) y
# además puede desincronizarse de la tabla real (ver el mismo bug que tenía
# `announcements/infrastructure/schemas.py` antes de este cambio). Agregar un
# rol nuevo ahora es solo una fila en `roles` — no requiere tocar este DTO.
EntityCode = Literal["hub", "lab", "ops"]


class StaffMemberDTO(BaseModel):
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
    # Entitlement EFECTIVO y vigente (override si lo hay, si no el
    # calculado) — fuente única: `absence_balances.entitled_days`.
    vacation_days_per_year: Optional[float]
    # Override manual del admin. `None` = automático (calculado desde
    # `hire_date`). Es el campo que el formulario de alta/edición usa para
    # decidir si el input de "días de vacaciones" debe mostrarse vacío
    # (automático) o con un valor (override vigente).
    vacation_days_override: Optional[float]
    # Lo que daría el cálculo automático ahora mismo, exista o no un
    # override — para mostrar "Calculado automáticamente: X días" en el
    # formulario sin reimplementar la fórmula de negocio en el frontend.
    vacation_days_calculated: float


class StaffMemberListDTO(BaseModel):
    members: list[StaffMemberDTO]
    total: int


class CreateStaffMemberDTO(BaseModel):
    full_name: str = Field(..., min_length=1)
    email: EmailStr
    job_title: Optional[str] = None
    department: Optional[str] = None
    entity: EntityCode
    role: str = Field(..., min_length=1)
    hire_date: Optional[date] = None
    # Vacío/`None` = automático (calculado desde `hire_date`); un número =
    # override manual. Sin ambigüedad posible en el alta (no hay estado
    # previo que "no tocar").
    vacation_days_override: Optional[float] = Field(None, ge=0)


class UpdateStaffMemberDTO(BaseModel):
    job_title: Optional[str] = None
    department: Optional[str] = None
    entity: Optional[EntityCode] = None
    role: Optional[str] = Field(None, min_length=1)
    # Campo AUSENTE del payload -> no toca el override; `vacation_days_override:
    # null` explícito -> lo vacía (vuelve a automático); un número -> lo fija.
    # La ruta distingue "ausente" de "null" con `dto.model_fields_set` (mismo
    # patrón que `holidays.entity`) — `Optional[float] = None` por sí solo
    # no puede.
    vacation_days_override: Optional[float] = Field(None, ge=0)
    is_active: Optional[bool] = None
