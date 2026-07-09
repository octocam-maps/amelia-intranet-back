"""Caso de uso: editar un festivo — fecha, nombre y ámbito (entidad).
Actualización parcial: solo se tocan los campos que llegan informados."""

from datetime import date
from typing import Optional

from ...domain.entities import Holiday
from ...domain.errors import HolidayNotFoundError, InvalidEntityCodeError
from ...domain.ports import IHolidayRepository

# Sentinela: distingue "no me pasaron entity_code" (no tocar el ámbito) de
# "me pasaron entity_code=None explícitamente" (vaciarlo -> aplica a todas).
_NOT_SET = object()


class UpdateHolidayUseCase:
    def __init__(self, repository: IHolidayRepository):
        self._repository = repository

    async def execute(
        self,
        holiday_id: str,
        *,
        day: Optional[date] = None,
        name: Optional[str] = None,
        scope: Optional[str] = None,
        entity_code: Optional[str] = _NOT_SET,  # type: ignore[assignment]
    ) -> Holiday:
        existing = await self._repository.find_by_id(holiday_id)
        if existing is None:
            raise HolidayNotFoundError("El festivo no existe.")

        entity_id: Optional[str] = None
        clear_entity = False
        if entity_code is not _NOT_SET:
            if entity_code is None:
                clear_entity = True
            else:
                entity_id = await self._repository.resolve_entity_id(entity_code)
                if entity_id is None:
                    raise InvalidEntityCodeError(f"La entidad '{entity_code}' no existe.")

        updated = await self._repository.update_holiday(
            holiday_id,
            day=day,
            name=name,
            scope=scope,
            entity_id=entity_id,
            clear_entity=clear_entity,
        )
        if updated is None:
            raise HolidayNotFoundError("El festivo no existe.")
        return updated
