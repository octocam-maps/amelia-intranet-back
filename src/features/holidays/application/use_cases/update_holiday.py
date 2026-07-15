"""Caso de uso: editar un festivo — fecha, nombre y ámbito (entidad).
Actualización parcial: solo se tocan los campos que llegan informados."""

from datetime import date
from typing import Optional

from ...domain.entities import Holiday
from ...domain.errors import (
    HolidayAlreadyExistsError,
    HolidayNotFoundError,
    InvalidEntityCodeError,
)
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
        # `entity_id`/`entity_code` que quedarán vigentes DESPUÉS de aplicar
        # esta actualización — se usan para la comprobación de duplicados de
        # abajo. Si no se informa `entity_code`, el ámbito no cambia.
        effective_entity_id = existing.entity_id
        effective_entity_code = existing.entity_code
        if entity_code is not _NOT_SET:
            if entity_code is None:
                clear_entity = True
                effective_entity_id = None
                effective_entity_code = None
            else:
                entity_id = await self._repository.resolve_entity_id(entity_code)
                if entity_id is None:
                    raise InvalidEntityCodeError(f"La entidad '{entity_code}' no existe.")
                effective_entity_id = entity_id
                effective_entity_code = entity_code

        effective_day = day if day is not None else existing.day

        # Misma validación que `CreateHolidayUseCase` (`uq_holiday_day_entity`):
        # sin esto, editar un festivo hacia una fecha/ámbito ya ocupados caía
        # en un 500 de Postgres en vez de un 409 legible (bug real, auditoría
        # QA). Se excluye el propio festivo que se está editando.
        collisions = await self._repository.list_holidays(
            year=effective_day.year, entity_code=effective_entity_code
        )
        if any(
            h.id != holiday_id and h.day == effective_day and h.entity_id == effective_entity_id
            for h in collisions
        ):
            raise HolidayAlreadyExistsError(
                "Ya existe un festivo en esa fecha para ese ámbito."
            )

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
