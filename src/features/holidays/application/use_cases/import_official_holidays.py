"""Caso de uso: importar los festivos oficiales de un año (exclusivo del
admin). Orquesta el proveedor externo (nacional España + autonómico Cataluña)
y el repositorio, que hace el upsert idempotente respetando los festivos
añadidos a mano. Los locales de Barcelona y los cierres de empresa NO vienen
de aquí — se siguen añadiendo manualmente."""

from ...domain.entities import ImportSummary
from ...domain.ports import IHolidayProvider, IHolidayRepository


class ImportOfficialHolidaysUseCase:
    def __init__(self, provider: IHolidayProvider, repository: IHolidayRepository):
        self._provider = provider
        self._repository = repository

    async def execute(self, *, year: int) -> ImportSummary:
        official = await self._provider.fetch_official_holidays(year)
        return await self._repository.import_official_holidays(official)
