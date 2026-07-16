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
    vacation_days_per_year: Optional[float]


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
    vacation_days_per_year: Optional[float] = Field(None, ge=0)


class UpdateStaffMemberDTO(BaseModel):
    job_title: Optional[str] = None
    department: Optional[str] = None
    entity: Optional[EntityCode] = None
    role: Optional[str] = Field(None, min_length=1)
    vacation_days_per_year: Optional[float] = Field(None, ge=0)
    is_active: Optional[bool] = None
