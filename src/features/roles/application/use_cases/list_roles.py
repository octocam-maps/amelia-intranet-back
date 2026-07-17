"""Caso de uso: listar los roles del sistema. Pass-through deliberado sobre
el repositorio — la tabla `roles` YA es la fuente única de verdad, este caso
de uso no filtra ni reordena nada (ver decisión en `domain/ports.py`)."""

from ...domain.entities import Role
from ...domain.ports import IRoleRepository


class ListRolesUseCase:
    def __init__(self, repository: IRoleRepository):
        self._repository = repository

    async def execute(self) -> list[Role]:
        return await self._repository.list_roles()
