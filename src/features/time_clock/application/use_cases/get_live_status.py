"""
Caso de uso: estado "en vivo" del fichaje (tramo/pausa abierto + total de la
semana) — alimenta la tarjeta grande de docs/deck-fase3/01-home-empleado.png
y el pill del topbar. Forma acordada con el frontend (ver `results.py`).
"""

from datetime import timedelta

from src.shared.utils.timezone import today_in_madrid

from ...domain.ports import ITimeClockRepository
from ..results import LiveClockStatusResult, OpenEntryStatus

# 40h/semana es el valor que el propio mockup muestra ("Esta semana Xh / 40h")
# — pendiente de que RRHH confirme si es configurable por jornada/contrato
# (mismo "pendiente" que el resto de constantes de negocio de esta fase).
_EXPECTED_WEEKLY_MINUTES = 40 * 60


class GetLiveStatusUseCase:
    def __init__(self, repository: ITimeClockRepository):
        self._repository = repository

    async def execute(self, *, user_id: str) -> LiveClockStatusResult:
        open_entry = await self._repository.find_open_entry_for_user(user_id)

        open_entry_status: OpenEntryStatus | None = None
        if open_entry is not None:
            open_break = await self._repository.find_open_break_for_entry(open_entry.id)
            open_entry_status = OpenEntryStatus(
                id=open_entry.id, clock_in=open_entry.clock_in, on_break=open_break is not None
            )

        today = today_in_madrid()
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        week_worked_seconds = await self._repository.get_week_worked_seconds(
            user_id, monday, sunday
        )

        return LiveClockStatusResult(
            open_entry=open_entry_status,
            week_worked_minutes=int(week_worked_seconds // 60),
            expected_weekly_minutes=_EXPECTED_WEEKLY_MINUTES,
        )
