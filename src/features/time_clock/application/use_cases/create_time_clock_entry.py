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
"""

from datetime import date, datetime
from typing import Optional

from ...domain.entities import TimeClockEntry
from ...domain.errors import InvalidTimeRangeError, TimeClockOverlapError
from ...domain.ports import ITimeClockRepository


class CreateTimeClockEntryUseCase:
    def __init__(self, repository: ITimeClockRepository):
        self._repository = repository

    async def execute(
        self,
        *,
        user_id: str,
        work_date: date,
        clock_in: datetime,
        clock_out: Optional[datetime],
        source: str = "web",
    ) -> TimeClockEntry:
        _validate_range(work_date, clock_in, clock_out)

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
            source=source,
        )


def _validate_range(work_date: date, clock_in: datetime, clock_out: Optional[datetime]) -> None:
    if clock_in.date() != work_date:
        raise InvalidTimeRangeError("La hora de entrada debe caer dentro de la fecha del tramo.")
    if clock_out is not None:
        if clock_out.date() != work_date:
            raise InvalidTimeRangeError("El tramo no puede cruzar de un día a otro.")
        if clock_out <= clock_in:
            raise InvalidTimeRangeError("La hora de salida debe ser posterior a la de entrada.")
