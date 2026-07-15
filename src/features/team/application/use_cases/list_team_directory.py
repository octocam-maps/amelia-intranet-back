"""Caso de uso: directorio de la plantilla. Visible para los 3 roles
(docs/permisos-roles.md § Equipo) — no hay filtrado por usuario porque
son campos ya considerados seguros de cara al RGPD."""

from ...domain.entities import TeamMember
from ...domain.ports import ITeamRepository


class ListTeamDirectoryUseCase:
    def __init__(self, repository: ITeamRepository):
        self._repository = repository

    async def execute(self) -> list[TeamMember]:
        return await self._repository.list_directory()
