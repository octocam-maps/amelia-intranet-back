"""Caso de uso: catálogo completo de tipos de ausencia, incluidos los
desactivados — vista de gestión del admin (docs/permisos-roles.md § "Tipos
de ausencia"). Distinto de `ListAbsenceTypesUseCase`, que solo devuelve los
activos para que el empleado elija al solicitar una ausencia."""

from ...domain.entities import AbsenceType
from ...domain.ports import IAbsenceRepository


class ListAllAbsenceTypesUseCase:
    def __init__(self, repository: IAbsenceRepository):
        self._repository = repository

    async def execute(self) -> list[AbsenceType]:
        return await self._repository.list_all_types()
