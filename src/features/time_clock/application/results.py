"""Resultados de los casos de uso de fichaje en vivo — no son entidades
persistidas, así que viven en `application`, no en `domain/entities.py`.

Forma acordada con el frontend (`amelia-intranet-web/src/features/time-clock/
domain/ports.ts`, comentario "contrato acordado con el backend"): un único
shape (`open_entry` + acumulado semanal) para `GET /time-clock/current` y las
4 acciones (`clock-in`, `clock-out`, `breaks/start`, `breaks/end`), todas
devuelven el estado recalculado tras el cambio."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from ..domain.entities import TimeClockEntry


@dataclass(frozen=True)
class OpenEntryStatus:
    id: str
    clock_in: datetime
    on_break: bool


@dataclass(frozen=True)
class LiveClockStatusResult:
    """Estado "en vivo" para pintar la tarjeta grande del dashboard y el pill
    del topbar (docs/deck-fase3/01-home-empleado.png)."""

    open_entry: Optional[OpenEntryStatus]
    week_worked_minutes: int
    expected_weekly_minutes: int


@dataclass(frozen=True)
class OmittedBatchDay:
    """Un día del rango del alta en lote (RF-A3) que no generó tramo, con
    su motivo (`TimeClockBatchOmissionReason`, serializado como `str`)."""

    work_date: date
    reason: str


@dataclass(frozen=True)
class TimeClockEntriesBatchResult:
    """Resultado del alta en lote — respuesta 200 SIEMPRE (nunca 201: el
    lote puede no crear nada y seguir siendo un resultado válido, ver
    EC4 de `CreateTimeClockEntriesBatchUseCase`)."""

    created: list[TimeClockEntry]
    omitted: list[OmittedBatchDay]


@dataclass(frozen=True)
class TechnicianMonthSummary:
    """Resumen de un mes del técnico: lo que pinta la tarjeta de bolsa y lo
    que encabeza el Excel mensual (requerimiento v1.2 §M1)."""

    year: int
    month: int
    budget_minutes: int
    worked_minutes: int
    overtime_minutes: int
    compensation_minutes: int
    overnight_stays_spain: int
    overnight_stays_abroad: int
    # `False` mientras el mes no ha terminado: su excedente todavía puede
    # cambiar, así que no devenga saldo (ver `GetCompensationBalanceUseCase`).
    is_closed: bool

    @property
    def remaining_minutes(self) -> int:
        """Lo que falta para agotar la bolsa. Cero —no negativo— cuando ya se
        ha superado: el exceso se comunica como `overtime_minutes`, y mezclar
        ambas cosas en un mismo número haría que la barra de progreso mintiera."""
        return max(0, self.budget_minutes - self.worked_minutes)

    @property
    def overnight_stays_total(self) -> int:
        return self.overnight_stays_spain + self.overnight_stays_abroad


@dataclass(frozen=True)
class CompensationBalance:
    """Saldo ANUAL de descanso por horas extra. Se calcula al vuelo: no hay
    tabla de saldos ni cierre de mes (decisión del team-lead del 2026-08-06).

    `accrued_minutes` solo suma MESES YA TERMINADOS. El mes en curso aparece
    aparte en `pending_minutes` para que la UI pueda enseñarlo sin que cuente
    como disponible — su excedente todavía puede cambiar con cualquier parte
    que se registre o corrija antes de fin de mes.
    """

    year: int
    accrued_minutes: int
    consumed_minutes: int
    pending_minutes: int

    @property
    def available_minutes(self) -> int:
        return self.accrued_minutes - self.consumed_minutes
