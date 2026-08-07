"""
Caso de uso: catálogo de proyectos activos para el desplegable del parte
diario (requerimiento v1.2 §M1).

Solo los activos: un proyecto cerrado no debe ofrecerse para imputar jornadas
nuevas, pero sigue existiendo en la tabla porque los partes históricos lo
referencian (`ON DELETE RESTRICT`).
"""

from ...domain.entities import Project
from ...domain.ports import ITimeClockRepository


class ListProjectsUseCase:
    def __init__(self, repository: ITimeClockRepository):
        self._repository = repository

    async def execute(self) -> list[Project]:
        return await self._repository.list_active_projects()
