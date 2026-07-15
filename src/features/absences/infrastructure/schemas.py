"""DTOs de request/response (Pydantic) del feature `absences`."""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field


class AbsenceTypeDTO(BaseModel):
    id: str
    code: str
    name: str
    is_paid: bool
    affects_balance: bool
    color: Optional[str] = None


class AbsenceTypeListDTO(BaseModel):
    types: list[AbsenceTypeDTO]


class AbsenceTypeAdminDTO(AbsenceTypeDTO):
    """Vista de gestión del admin — añade lo que `AbsenceTypeDTO` (usado al
    elegir tipo en el modal de solicitud) no necesita mostrar al empleado."""

    default_entitled_days: float
    is_active: bool
    requires_approval: bool
    requires_justification: bool
    max_days_per_year: Optional[int]


class AbsenceTypeAdminListDTO(BaseModel):
    types: list[AbsenceTypeAdminDTO]


class CreateAbsenceTypeDTO(BaseModel):
    code: str = Field(..., min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")
    name: str = Field(..., min_length=1, max_length=120)
    is_paid: bool = True
    affects_balance: bool = True
    default_entitled_days: float = Field(0, ge=0)
    color: Optional[str] = None
    requires_approval: bool = True
    requires_justification: bool = False
    max_days_per_year: Optional[int] = Field(None, ge=0)


class UpdateAbsenceTypeDTO(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    is_paid: Optional[bool] = None
    affects_balance: Optional[bool] = None
    default_entitled_days: Optional[float] = Field(None, ge=0)
    color: Optional[str] = None
    is_active: Optional[bool] = None
    requires_approval: Optional[bool] = None
    requires_justification: Optional[bool] = None
    max_days_per_year: Optional[int] = Field(None, ge=0)


class AbsenceBalanceDTO(BaseModel):
    absence_type_id: str
    year: int
    entitled_days: float
    used_days: float
    pending_days: float
    available_days: float


class AbsenceBalanceListDTO(BaseModel):
    balances: list[AbsenceBalanceDTO]


class CreateAbsenceRequestDTO(BaseModel):
    absence_type_id: str
    start_date: date
    end_date: date
    reason: Optional[str] = None


class ReviewAbsenceRequestDTO(BaseModel):
    decision: Literal["approved", "rejected"]
    note: Optional[str] = None


class AbsenceRequestDTO(BaseModel):
    id: str
    user_id: str
    absence_type_id: str
    start_date: date
    end_date: date
    days_count: float
    reason: Optional[str]
    status: str
    reviewed_by: Optional[str]
    review_note: Optional[str]
    # Solo viene relleno en `/requests/pending` y `/requests/all` (JOIN con
    # `users`) — mismo nombre de campo que `dashboard.PendingAbsenceRequestDTO`.
    user_full_name: Optional[str] = None


class AbsenceRequestListDTO(BaseModel):
    requests: list[AbsenceRequestDTO]
