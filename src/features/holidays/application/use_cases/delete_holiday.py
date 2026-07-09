"""Caso de uso: borrar un festivo (exclusivo del admin). Borrado físico —
nada referencia `holidays` con FK (`features/absences` solo lee por rango de
fecha), no hace falta soft-delete aquí."""

from ...domain.errors import HolidayNotFoundError
from ...domain.ports import IHolidayRepository


class DeleteHolidayUseCase:
    def __init__(self, repository: IHolidayRepository):
        self._repository = repository

    async def execute(self, holiday_id: str) -> None:
        deleted = await self._repository.delete_holiday(holiday_id)
        if not deleted:
            raise HolidayNotFoundError("El festivo no existe.")
