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
    # `None` fuera de los listados paginados (alta, edición, fichaje en
    # vivo...) — solo `GET /entries` lo rellena vía JOIN a `users`.
    full_name: Optional[str] = None
    work_date: date
    clock_in: datetime
    clock_out: Optional[datetime]
    source: str
    worked_minutes: Optional[int]


class TimeClockEntryListDTO(BaseModel):
    entries: list[TimeClockEntryDTO]
    total: int
    limit: int
    offset: int


class OpenTimeClockEntryDTO(BaseModel):
    id: str
    clock_in: datetime
    on_break: bool


class AddTimeClockEntryNoteDTO(BaseModel):
    """Alta de una incidencia/comentario sobre un tramo (B-2b, admin-only —
    el guard de rol vive en el router)."""

    body: str


class TimeClockEntryNoteDTO(BaseModel):
    id: str
    entry_id: str
    # `None` si el autor fue eliminado (`ON DELETE SET NULL`).
    author_id: Optional[str]
    author_full_name: Optional[str]
    body: str
    created_at: datetime


class TimeClockEntryNoteListDTO(BaseModel):
    notes: list[TimeClockEntryNoteDTO]


class TimeClockCurrentStatusDTO(BaseModel):
    """Estado en vivo del fichaje — contrato acordado con el frontend
    (`time-clock/domain/ports.ts`): un único shape para `GET /current` y las
    4 acciones (clock-in/out, breaks/start/end), todas devuelven el estado
    recalculado tras el cambio. Alimenta la tarjeta grande del dashboard y
    el pill del topbar (docs/deck-fase3/01-home-empleado.png)."""

    open_entry: Optional[OpenTimeClockEntryDTO]
    week_worked_minutes: int
    expected_weekly_minutes: int
