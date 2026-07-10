"""
Caso de uso: job por-tiempo — fichajes sin salida al cierre de la jornada
(docs/requerimientos-amelia-intranet.pdf §6). El control horario de esta
intranet es por SELECCIÓN MANUAL DE TRAMOS (ver
`features/time_clock/domain/entities.py`), así que un tramo con `clock_out
IS NULL` de un `work_date` YA CERRADO es, por definición, una salida que el
trabajador olvidó registrar — no una jornada todavía en curso.
"""

from datetime import date, timedelta
from typing import Optional

from ...domain.ports import INotificationRepository
from .notify import NotifyUseCase


class RunClockOutNotificationJobUseCase:
    def __init__(self, repository: INotificationRepository, notify: NotifyUseCase):
        self._repository = repository
        self._notify = notify

    async def execute(self, *, work_date: Optional[date] = None) -> dict:
        # Por defecto revisa AYER: un tramo abierto de HOY todavía puede
        # cerrarse en lo que queda de jornada, no es "olvidado" todavía.
        target_date = work_date or (date.today() - timedelta(days=1))
        user_ids = await self._repository.list_user_ids_with_open_entry(target_date)

        for user_id in user_ids:
            await self._notify.execute(
                recipient_ids=[user_id],
                type="clock_out_missing",
                title="No registraste tu salida",
                body=f"El {target_date.strftime('%d/%m/%Y')} fichaste entrada pero no salida.",
                data={"work_date": target_date.isoformat(), "url": "/control-horario"},
            )

        return {"work_date": target_date.isoformat(), "users_notified": len(user_ids)}
