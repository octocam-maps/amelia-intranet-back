"""
Caso de uso: registrar un tramo de fichaje (entrada/salida elegidas
manualmente). Reglas de negocio:
- Ambas horas deben caer dentro de `work_date` — el tramo no cruza medianoche
  (si RRHH confirma turnos nocturnos, se revisita esta regla).
- Un tramo puede crearse "abierto" (`clock_out=None`) y cerrarse después con
  `UpdateTimeClockEntryUseCase`.
- No puede solaparse con otro tramo ya registrado ese día para el mismo
  usuario — el backend es la única fuente de verdad, aunque la UI también lo
  valide antes de enviar la petición.
- LOGIC-2 (pentest ético, severidad ALTA): `work_date` no puede ser futura ni
  más antigua que `manual_entry_max_past_days` — RRHH decidió conservar el
  alta manual ("me olvidé de fichar") en vez de restringirla a admin, así que
  se blinda con una ventana temporal en vez de eliminarla. Además, el `source`
  persistido es SIEMPRE `TimeClockSource.MANUAL`, nunca lo que pida el
  llamador — distingue este alta del fichaje en vivo (`ClockInUseCase`,
  `source="live"`) para que RRHH pueda auditar horas autodeclaradas frente a
  fichadas en tiempo real (antes ambos escribían el mismo `"web"` histórico).
"""

from datetime import date, datetime, timedelta
from typing import Optional

from src.shared.utils.timezone import today_in_madrid

from ...domain.entities import TimeClockEntry, TimeClockSource
from ...domain.errors import (
    InvalidTimeRangeError,
    ManualEntryOutOfWindowError,
    TimeClockOverlapError,
)
from ...domain.ports import ITimeClockRepository


class CreateTimeClockEntryUseCase:
    def __init__(self, repository: ITimeClockRepository, manual_entry_max_past_days: int):
        self._repository = repository
        self._manual_entry_max_past_days = manual_entry_max_past_days

    async def execute(
        self,
        *,
        user_id: str,
        work_date: date,
        clock_in: datetime,
        clock_out: Optional[datetime],
    ) -> TimeClockEntry:
        _validate_range(work_date, clock_in, clock_out)
        self._validate_window(work_date)

        overlapping = await self._repository.find_overlapping_entry(
            user_id, work_date, clock_in, clock_out
        )
        if overlapping is not None:
            raise TimeClockOverlapError(
                "Ese tramo se solapa con otro fichaje ya registrado ese día."
            )

        return await self._repository.create_entry(
            user_id=user_id,
            work_date=work_date,
            clock_in=clock_in,
            clock_out=clock_out,
            source=TimeClockSource.MANUAL,
        )

    def _validate_window(self, work_date: date) -> None:
        today = today_in_madrid()
        if work_date > today:
            raise ManualEntryOutOfWindowError(
                "No puedes registrar un tramo con fecha futura."
            )
        oldest_allowed = today - timedelta(days=self._manual_entry_max_past_days)
        if work_date < oldest_allowed:
            raise ManualEntryOutOfWindowError(
                "No puedes registrar un tramo de hace más de "
                f"{self._manual_entry_max_past_days} días."
            )


def _validate_range(work_date: date, clock_in: datetime, clock_out: Optional[datetime]) -> None:
    if clock_in.date() != work_date:
        raise InvalidTimeRangeError("La hora de entrada debe caer dentro de la fecha del tramo.")
    if clock_out is not None:
        if clock_out.date() != work_date:
            raise InvalidTimeRangeError("El tramo no puede cruzar de un día a otro.")
        if clock_out <= clock_in:
            raise InvalidTimeRangeError("La hora de salida debe ser posterior a la de entrada.")
