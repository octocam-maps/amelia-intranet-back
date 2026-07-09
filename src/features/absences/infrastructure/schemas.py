"""DTOs de request/response (Pydantic) del feature `absences`."""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel


class AbsenceTypeDTO(BaseModel):
    id: str
    code: str
    name: str
    is_paid: bool
    affects_balance: bool
    color: Optional[str] = None


class AbsenceTypeListDTO(BaseModel):
    types: list[AbsenceTypeDTO]


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


class AbsenceRequestListDTO(BaseModel):
    requests: list[AbsenceRequestDTO]
