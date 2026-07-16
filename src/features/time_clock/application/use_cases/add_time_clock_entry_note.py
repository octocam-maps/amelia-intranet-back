"""
Caso de uso: dejar una incidencia/comentario sobre un tramo de fichaje
(B-2b). RBAC: el guard de rol (solo admin) vive en el router
(`require_role("administrador")`) — este caso de uso no lo repite, igual
que `ReviewAbsenceRequestUseCase` para las acciones admin-only de ausencias.
"""

from ...domain.entities import TimeClockEntryNote
from ...domain.errors import TimeClockEntryNotFoundError, TimeClockNoteBodyRequiredError
from ...domain.ports import ITimeClockRepository


class AddTimeClockEntryNoteUseCase:
    def __init__(self, repository: ITimeClockRepository):
        self._repository = repository

    async def execute(self, *, entry_id: str, author_id: str, body: str) -> TimeClockEntryNote:
        entry = await self._repository.find_entry_by_id(entry_id)
        if entry is None:
            raise TimeClockEntryNotFoundError("El tramo de fichaje no existe.")

        stripped_body = body.strip()
        if not stripped_body:
            raise TimeClockNoteBodyRequiredError("La incidencia no puede estar vacía.")

        return await self._repository.add_note(
            entry_id=entry_id, author_id=author_id, body=stripped_body
        )
