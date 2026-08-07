"""
Caso de uso: eliminar un parte diario.

Borra el tramo padre de `time_clock_entries`; el `ON DELETE CASCADE` del
satélite se lleva el detalle de campo. Mismo alcance que la edición: el
técnico borra los suyos, el administrador los de cualquiera.

Consecuencia que hay que tener presente: al no existir cierre de mes, borrar
un parte de un mes ya terminado RECALCULA el saldo de compensación de ese año.
La ventana de `TIME_CLOCK_MANUAL_ENTRY_MAX_PAST_DAYS` (30 días por defecto)
acota cuánto hacia atrás puede llegar el efecto, pero no lo elimina.
"""

from src.shared.auth.roles import RoleCode

from ...domain.errors import TechnicianDailyLogNotFoundError, TimeClockForbiddenError
from ...domain.ports import ITimeClockRepository


class DeleteTechnicianDailyLogUseCase:
    def __init__(self, repository: ITimeClockRepository):
        self._repository = repository

    async def execute(
        self, *, entry_id: str, requester_id: str, requester_role: str
    ) -> None:
        existing = await self._repository.find_daily_log(entry_id)
        if existing is None:
            raise TechnicianDailyLogNotFoundError(
                "No existe un parte con ese identificador."
            )

        if (
            requester_role != RoleCode.ADMINISTRADOR
            and existing.user_id != requester_id
        ):
            raise TimeClockForbiddenError("Solo puedes eliminar tus propios partes.")

        await self._repository.delete_daily_log(entry_id)
