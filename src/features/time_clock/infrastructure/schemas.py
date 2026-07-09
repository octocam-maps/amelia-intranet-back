"""DTOs de request/response (Pydantic) del feature `time_clock`."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class CreateTimeClockEntryDTO(BaseModel):
    work_date: date
    clock_in: datetime
    clock_out: Optional[datetime] = None


class UpdateTimeClockEntryDTO(BaseModel):
    clock_in: datetime
    clock_out: Optional[datetime] = None


class TimeClockEntryDTO(BaseModel):
    id: str
    user_id: str
    work_date: date
    clock_in: datetime
    clock_out: Optional[datetime]
    source: str
    worked_minutes: Optional[int]


class TimeClockEntryListDTO(BaseModel):
    entries: list[TimeClockEntryDTO]
