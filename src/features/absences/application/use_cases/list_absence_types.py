"""Caso de uso: catálogo de tipos de ausencia configurados (el admin los edita en Fase 5)."""

from ...domain.entities import AbsenceType
from ...domain.ports import IAbsenceRepository


class ListAbsenceTypesUseCase:
    def __init__(self, repository: IAbsenceRepository):
        self._repository = repository

    async def execute(self) -> list[AbsenceType]:
        return await self._repository.list_types()
