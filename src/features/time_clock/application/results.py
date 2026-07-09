"""Resultados de los casos de uso de fichaje en vivo — no son entidades
persistidas, así que viven en `application`, no en `domain/entities.py`.

Forma acordada con el frontend (`amelia-intranet-web/src/features/time-clock/
domain/ports.ts`, comentario "contrato acordado con el backend"): un único
shape (`open_entry` + acumulado semanal) para `GET /time-clock/current` y las
4 acciones (`clock-in`, `clock-out`, `breaks/start`, `breaks/end`), todas
devuelven el estado recalculado tras el cambio."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


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
