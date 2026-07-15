"""DTOs de request/response (Pydantic) del feature `staff`."""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field

RoleCode = Literal["administrador", "empleado", "externo_invitado"]
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
    role: RoleCode
    hire_date: Optional[date] = None
    vacation_days_per_year: Optional[float] = Field(None, ge=0)


class UpdateStaffMemberDTO(BaseModel):
    job_title: Optional[str] = None
    department: Optional[str] = None
    entity: Optional[EntityCode] = None
    role: Optional[RoleCode] = None
    vacation_days_per_year: Optional[float] = Field(None, ge=0)
    is_active: Optional[bool] = None
