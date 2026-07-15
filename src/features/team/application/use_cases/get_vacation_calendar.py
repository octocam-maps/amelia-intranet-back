"""Caso de uso: calendario de vacaciones APROBADAS del equipo para un mes
concreto. Visible para los 3 roles (docs/permisos-roles.md § Equipo) — solo
lectura, sin acciones de aprobación (eso es exclusivo de `absences`)."""

from ...domain.entities import VacationCalendarEntry
from ...domain.ports import ITeamRepository


class GetVacationCalendarUseCase:
    def __init__(self, repository: ITeamRepository):
        self._repository = repository

    async def execute(self, *, year: int, month: int) -> list[VacationCalendarEntry]:
        return await self._repository.list_approved_vacations(year, month)
