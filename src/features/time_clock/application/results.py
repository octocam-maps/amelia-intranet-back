"""Resultados de los casos de uso de fichaje en vivo — no son entidades
persistidas, así que viven en `application`, no en `domain/entities.py`."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class LiveClockStatusResult:
    """Estado "en vivo" para pintar la tarjeta grande del dashboard
    (docs/deck-fase3/01-home-empleado.png): timer, botones Pausa/Fichar
    salida y "Esta semana Xh/40h"."""

    has_open_entry: bool
    clock_in: Optional[datetime]
    has_open_break: bool
    break_start: Optional[datetime]
    worked_seconds_today: float
    week_worked_seconds: float
    week_target_seconds: float
