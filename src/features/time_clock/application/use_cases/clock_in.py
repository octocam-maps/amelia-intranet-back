"""
Caso de uso: fichar entrada en vivo (botón play del dashboard,
docs/deck-fase3/01-home-empleado.png) — modelo "ambos": complementa el alta
manual de tramos (`CreateTimeClockEntryUseCase`) sin sustituirla. Abre un
tramo con `clock_in=ahora` y `clock_out=None`; se cierra con
`ClockOutUseCase`.
"""

from datetime import datetime, timezone

from ...domain.entities import TimeClockEntry, TimeClockSource
from ...domain.errors import TimeClockAlreadyClockedInError
from ...domain.ports import ITimeClockRepository
from src.shared.utils.timezone import today_in_madrid


class ClockInUseCase:
    def __init__(self, repository: ITimeClockRepository):
        self._repository = repository

    async def execute(self, *, user_id: str) -> TimeClockEntry:
        open_entry = await self._repository.find_open_entry_for_user(user_id)
        if open_entry is not None:
            raise TimeClockAlreadyClockedInError(
                "Ya tienes un fichaje en curso — ficha salida antes de volver a entrar."
            )

        now = datetime.now(timezone.utc)
        return await self._repository.create_entry(
            user_id=user_id,
            work_date=today_in_madrid(),
            clock_in=now,
            clock_out=None,
            # LOGIC-2 (pentest ético): distingue el fichaje en vivo del alta
            # manual (`CreateTimeClockEntryUseCase`, `source="manual"`) —
            # antes ambos escribían "web" y RRHH no podía auditar cuántas
            # horas eran autodeclaradas.
            source=TimeClockSource.LIVE,
        )
