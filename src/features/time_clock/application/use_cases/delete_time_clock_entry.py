"""Caso de uso: eliminar un tramo de fichaje. RBAC: solo el dueño o el admin."""

from src.shared.auth.roles import RoleCode

from ...domain.errors import TimeClockEntryNotFoundError, TimeClockForbiddenError
from ...domain.ports import ITimeClockRepository


class DeleteTimeClockEntryUseCase:
    def __init__(self, repository: ITimeClockRepository):
        self._repository = repository

    async def execute(self, *, entry_id: str, requester_id: str, requester_role: str) -> None:
        entry = await self._repository.find_entry_by_id(entry_id)
        if entry is None:
            raise TimeClockEntryNotFoundError("El tramo de fichaje no existe.")

        if requester_role != RoleCode.ADMINISTRADOR and entry.user_id != requester_id:
            raise TimeClockForbiddenError("No puedes eliminar el fichaje de otro usuario.")

        await self._repository.delete_entry(entry_id)
