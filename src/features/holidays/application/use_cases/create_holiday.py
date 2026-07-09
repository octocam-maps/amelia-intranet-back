"""Caso de uso: marcar un festivo (exclusivo del admin,
docs/permisos-roles.md § "Festivos": "Marcar anualmente los festivos
vigentes"). `entity_code=None` marca el festivo como aplicable a las 3
entidades (`holidays.entity_id IS NULL`)."""

from datetime import date
from typing import Optional

from ...domain.entities import Holiday
from ...domain.errors import HolidayAlreadyExistsError, InvalidEntityCodeError
from ...domain.ports import IHolidayRepository


class CreateHolidayUseCase:
    def __init__(self, repository: IHolidayRepository):
        self._repository = repository

    async def execute(
        self, *, day: date, name: str, entity_code: Optional[str]
    ) -> Holiday:
        entity_id = None
        if entity_code:
            entity_id = await self._repository.resolve_entity_id(entity_code)
            if entity_id is None:
                raise InvalidEntityCodeError(f"La entidad '{entity_code}' no existe.")

        existing = await self._repository.list_holidays(year=day.year, entity_code=entity_code)
        if any(h.day == day and h.entity_id == entity_id for h in existing):
            raise HolidayAlreadyExistsError(
                "Ya existe un festivo en esa fecha para ese ámbito."
            )

        return await self._repository.create_holiday(day=day, name=name, entity_id=entity_id)
