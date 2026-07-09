"""
Caso de uso: estado "en vivo" del fichaje (tramo/pausa abierto + total de la
semana) — alimenta la tarjeta grande de docs/deck-fase3/01-home-empleado.png.
"""

from datetime import timedelta

from src.shared.utils.timezone import today_in_madrid

from ...domain.ports import ITimeClockRepository
from ..results import LiveClockStatusResult

# 40h/semana es el valor que el propio mockup muestra ("Esta semana Xh / 40h")
# — pendiente de que RRHH confirme si es configurable por jornada/contrato
# (mismo "pendiente" que el resto de constantes de negocio de esta fase).
_WEEKLY_TARGET_SECONDS = 40 * 3600


class GetLiveStatusUseCase:
    def __init__(self, repository: ITimeClockRepository):
        self._repository = repository

    async def execute(self, *, user_id: str) -> LiveClockStatusResult:
        open_entry = await self._repository.find_open_entry_for_user(user_id)
        open_break = (
            await self._repository.find_open_break_for_entry(open_entry.id)
            if open_entry is not None
            else None
        )

        today = today_in_madrid()
        worked_seconds_today = await self._repository.get_week_worked_seconds(
            user_id, today, today
        )

        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        week_worked_seconds = await self._repository.get_week_worked_seconds(
            user_id, monday, sunday
        )

        return LiveClockStatusResult(
            has_open_entry=open_entry is not None,
            clock_in=open_entry.clock_in if open_entry else None,
            has_open_break=open_break is not None,
            break_start=open_break.break_start if open_break else None,
            worked_seconds_today=worked_seconds_today,
            week_worked_seconds=week_worked_seconds,
            week_target_seconds=float(_WEEKLY_TARGET_SECONDS),
        )
