"""DTOs de request/response (Pydantic) del feature `time_clock`."""

from datetime import date, datetime, time
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


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


class CreateTimeClockEntriesBatchDTO(BaseModel):
    """Alta en lote (RF-A3): `clock_in_time`/`clock_out_time` son hora de
    PARED Europe/Madrid, SIN offset — a diferencia de `CreateTimeClockEntryDTO`
    (`TZ-1`, offset obligatorio), el lote aplica UN MISMO horario a varios
    días y exigir offset por día obligaría al cliente a convertir N veces en
    vez de una. El backend ancla la hora a Madrid en el use case, igual que
    ya hace `today_in_madrid()` en el resto del feature."""

    date_from: date
    date_to: date
    clock_in_time: time
    clock_out_time: time | None = None


class OmittedBatchDayDTO(BaseModel):
    work_date: date
    reason: str


class TimeClockEntriesBatchDTO(BaseModel):
    """Respuesta del alta en lote — SIEMPRE 200 (nunca 201: el lote puede no
    crear nada y seguir siendo un resultado válido, p.ej. una ausencia
    aprobada que cubre todo el rango)."""

    created: list[TimeClockEntryDTO]
    omitted: list[OmittedBatchDayDTO]


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


# --- Parte diario del técnico (requerimiento v1.2 §M1) ---


class TechnicianDailyLogInputDTO(BaseModel):
    """Campos que RRHH pidió literalmente. `worked_minutes` NO está aquí a
    propósito: es un cálculo del backend y aceptarlo del cliente permitiría
    declarar 4 horas en una jornada de 12 — justo el dato del que cuelga toda
    la bolsa de 162 h."""

    work_date: date
    started_at: datetime
    ended_at: datetime
    project_id: str
    work_location: str = Field(min_length=2, max_length=160)
    had_break: bool
    break_minutes: int = Field(default=0, ge=0)
    # La UI pregunta en dos pasos (¿hubo pernocta? → ¿España o fuera?) y mapea
    # a este único valor: así "no hubo pernocta pero fue en España" no existe.
    overnight_stay: Literal["ninguna", "espana", "extranjero"] = "ninguna"
    product_category: Literal["software", "hardware"]

    @field_validator("started_at", "ended_at")
    @classmethod
    def _validate_offset(cls, value: datetime) -> datetime:
        # Mismo TZ-1 que el resto del feature. Aquí es todavía más importante:
        # sin offset, una jornada que termina "a las 01:30" es irresoluble
        # entre el día que empieza y el siguiente.
        return _require_offset(value)

    @field_validator("work_location")
    @classmethod
    def _strip_location(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 2:
            raise ValueError("Indica el lugar de trabajo.")
        return stripped


class UpdateTechnicianDailyLogDTO(TechnicianDailyLogInputDTO):
    """`work_date` se hereda pero el caso de uso la IGNORA: cambiarla movería
    el parte de mes y con él el cómputo de la bolsa. Para eso se borra y se
    crea de nuevo."""


class TechnicianDailyLogDTO(BaseModel):
    entry_id: str
    user_id: str
    full_name: Optional[str] = None
    work_date: date
    started_at: datetime
    ended_at: datetime
    project_id: str
    project_name: Optional[str] = None
    work_location: str
    had_break: bool
    break_minutes: int
    overnight_stay: str
    product_category: str
    worked_minutes: int


class TechnicianMonthSummaryDTO(BaseModel):
    year: int
    month: int
    budget_minutes: int
    worked_minutes: int
    remaining_minutes: int
    overtime_minutes: int
    compensation_minutes: int
    overnight_stays_spain: int
    overnight_stays_abroad: int
    overnight_stays_total: int
    is_closed: bool


class TechnicianDailyLogListDTO(BaseModel):
    logs: list[TechnicianDailyLogDTO]
    summary: TechnicianMonthSummaryDTO


class CompensationBalanceDTO(BaseModel):
    """Saldo ANUAL. `pending_minutes` es lo que devengaría el mes en curso si
    terminara hoy — se envía aparte para que la UI pueda mostrarlo sin
    contarlo como disponible."""

    year: int
    accrued_minutes: int
    consumed_minutes: int
    available_minutes: int
    pending_minutes: int


class ProjectDTO(BaseModel):
    id: str
    code: str
    name: str


class ProjectListDTO(BaseModel):
    projects: list[ProjectDTO]
