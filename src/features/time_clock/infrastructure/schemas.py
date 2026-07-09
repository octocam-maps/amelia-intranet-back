"""DTOs de request/response (Pydantic) del feature `time_clock`."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, field_validator


def _require_offset(value: Optional[datetime]) -> Optional[datetime]:
    # TZ-1 (auditoría QA Fase 3): un datetime SIN offset es ambiguo — no
    # sabemos si el front lo mandó en hora local del navegador o ya en UTC.
    # Se exige que el front mande siempre el offset explícito (p.ej.
    # `2026-07-06T09:00:00Z` o `...+02:00`); Postgres lo normaliza a UTC al
    # guardarlo en la columna TIMESTAMPTZ.
    if value is not None and value.tzinfo is None:
        raise ValueError(
            "La fecha/hora debe incluir el offset de zona horaria (UTC explícito)."
        )
    return value


class CreateTimeClockEntryDTO(BaseModel):
    work_date: date
    clock_in: datetime
    clock_out: Optional[datetime] = None

    @field_validator("clock_in", "clock_out")
    @classmethod
    def _validate_offset(cls, value: Optional[datetime]) -> Optional[datetime]:
        return _require_offset(value)


class UpdateTimeClockEntryDTO(BaseModel):
    clock_in: datetime
    clock_out: Optional[datetime] = None

    @field_validator("clock_in", "clock_out")
    @classmethod
    def _validate_offset(cls, value: Optional[datetime]) -> Optional[datetime]:
        return _require_offset(value)


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


class TimeClockBreakDTO(BaseModel):
    id: str
    entry_id: str
    break_start: datetime
    break_end: Optional[datetime]


class LiveClockStatusDTO(BaseModel):
    """Estado en vivo del fichaje — tarjeta grande del dashboard
    (docs/deck-fase3/01-home-empleado.png)."""

    has_open_entry: bool
    clock_in: Optional[datetime]
    has_open_break: bool
    break_start: Optional[datetime]
    worked_seconds_today: float
    week_worked_seconds: float
    week_target_seconds: float
