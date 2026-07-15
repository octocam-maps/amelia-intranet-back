"""Caso de uso: listado paginado de la plantilla (exclusivo del admin,
docs/deck-fase6/09-plantilla-listado.png)."""

from typing import Optional

from ...domain.entities import StaffMember
from ...domain.ports import IStaffRepository


class ListStaffUseCase:
    def __init__(self, repository: IStaffRepository):
        self._repository = repository

    async def execute(
        self,
        *,
        entity_code: Optional[str],
        search: Optional[str],
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[StaffMember], int]:
        members = await self._repository.list_staff(
            entity_code=entity_code, search=search, page=page, page_size=page_size
        )
        total = await self._repository.count_staff(entity_code=entity_code, search=search)
        return members, total
