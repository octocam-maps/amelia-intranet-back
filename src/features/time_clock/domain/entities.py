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
class TimeClockExportRow:
    """Una fila del informe de fichajes exportable a XLSX (vista admin,
    TODA la plantilla interna — `docs/permisos-roles.md` § Control horario).

    A diferencia de `TimeClockEntry`, esta forma SÍ conoce identidad/contacto
    porque es el resultado de un informe de RRHH (join con `users` +
    `user_profiles`), no la entidad transaccional del fichaje. Mismo patrón
    que `UserProfile` en el feature `profile`: un join resuelto en el
    repositorio, expuesto como forma de dominio porque el puerto
    (`ITimeClockRepository`) vive en `domain`.

    `full_name` es un único campo de texto en `users` (no hay columnas
    Nombre/Apellido separadas) — la capa de infraestructura que construye el
    libro XLSX reparte "Nombre = primera palabra, Apellido = el resto"
    (`infrastructure/xlsx_export.py::_split_full_name`), la MISMA heurística
    que ya usa `ORDER BY` en el repositorio para que la fila y el orden
    coincidan.
    """

    user_id: str
    full_name: str
    dni_nif: Optional[str]
    phone: Optional[str]
    work_date: date
    clock_in: datetime
    clock_out: Optional[datetime]

    @property
    def worked_minutes(self) -> Optional[int]:
        """`None` si el tramo sigue abierto (fichaje en curso, sin salida)."""
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
