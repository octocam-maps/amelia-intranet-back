"""Caso de uso: listar los departamentos existentes. Pass-through
deliberado sobre el repositorio — igual que `ListRolesUseCase` en el
feature `roles`, no filtra ni reordena nada; ese trabajo ya lo hace la
query SQL (`ORDER BY name`)."""

from ...domain.entities import Department
from ...domain.ports import IDepartmentRepository


class ListDepartmentsUseCase:
    def __init__(self, repository: IDepartmentRepository):
        self._repository = repository

    async def execute(self) -> list[Department]:
        return await self._repository.list_departments()
