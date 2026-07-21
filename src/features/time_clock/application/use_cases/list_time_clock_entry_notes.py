"""
Caso de uso: listar las incidencias/comentarios de un tramo de fichaje
(B-2b). RBAC: el dueño del tramo puede ver sus propias incidencias; el admin
puede ver las de cualquiera — mismo criterio de alcance que
`UpdateTimeClockEntryUseCase`/`DeleteTimeClockEntryUseCase`.
"""

from src.shared.auth.roles import RoleCode

from ...domain.entities import TimeClockEntryNote
from ...domain.errors import TimeClockEntryNotFoundError, TimeClockForbiddenError
from ...domain.ports import ITimeClockRepository


class ListTimeClockEntryNotesUseCase:
    def __init__(self, repository: ITimeClockRepository):
        self._repository = repository

    async def execute(
        self, *, entry_id: str, requester_id: str, requester_role: str
    ) -> list[TimeClockEntryNote]:
        entry = await self._repository.find_entry_by_id(entry_id)
        if entry is None:
            raise TimeClockEntryNotFoundError("El tramo de fichaje no existe.")

        if requester_role != RoleCode.ADMINISTRADOR and entry.user_id != requester_id:
            raise TimeClockForbiddenError(
                "No puedes ver las incidencias del fichaje de otro usuario."
            )

        return await self._repository.list_notes_for_entry(entry_id)
