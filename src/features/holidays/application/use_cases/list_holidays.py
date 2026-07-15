"""Caso de uso: calendario de festivos, opcionalmente filtrado por año y
entidad (docs/permisos-roles.md § "Festivos"). Lectura compartida por admin
y empleado — el externo-invitado no tiene "Ausencias"/"Inicio" en la matriz
de permisos, la ruta ya lo bloquea antes de llegar aquí."""

from typing import Optional

from ...domain.entities import Holiday
from ...domain.ports import IHolidayRepository


class ListHolidaysUseCase:
    def __init__(self, repository: IHolidayRepository):
        self._repository = repository

    async def execute(
        self, *, year: Optional[int] = None, entity_code: Optional[str] = None
    ) -> list[Holiday]:
        return await self._repository.list_holidays(year=year, entity_code=entity_code)
