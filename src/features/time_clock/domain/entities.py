"""Entidades de dominio del feature `time_clock`. Sin dependencias de framework/SQL."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


@dataclass(frozen=True)
class TimeClockEntry:
    """Un tramo de fichaje (entrada/salida elegidas manualmente por el usuario).

    El control horario de Amelia intranet es por SELECCIÓN MANUAL DE TRAMOS
    (p.ej. "de 6 a 9"), no un fichaje en tiempo real con pulsación de botón
    (decisión cerrada en la demo). Un mismo `work_date` puede tener varios
    tramos (mañana/tarde); el hueco entre dos tramos YA actúa como pausa
    implícita, así que este feature no usa todavía `time_clock_breaks` (existe
    desde 003_hr_core, sin endpoints) — si RRHH pide registrar pausas DENTRO
    de un mismo tramo, se retoma sin migración nueva.
    """

    id: str
    user_id: str
    work_date: date
    clock_in: datetime
    clock_out: Optional[datetime]
    source: str
    created_at: datetime
    updated_at: datetime

    @property
    def worked_minutes(self) -> Optional[int]:
        """`None` si el tramo sigue abierto (`clock_out` sin fijar todavía)."""
        if self.clock_out is None:
            return None
        return int((self.clock_out - self.clock_in).total_seconds() // 60)


@dataclass(frozen=True)
class TimeClockBreak:
    """Una pausa DENTRO de un tramo abierto — modelo "en vivo" (botón
    Pausa/Reanudar del dashboard, docs/deck-fase3/01-home-empleado.png).

    A diferencia del fichaje manual por tramos (donde el hueco ENTRE dos
    tramos ya actúa como pausa implícita, ver `TimeClockEntry`), aquí sí se
    usa `time_clock_breaks` porque la pausa ocurre DENTRO de un mismo tramo
    que sigue abierto — parar el timer sin cerrar la jornada.
    """

    id: str
    entry_id: str
    break_start: datetime
    break_end: Optional[datetime]

    @property
    def is_open(self) -> bool:
        return self.break_end is None
