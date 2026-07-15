"""Caso de uso: calendario de ausencias APROBADAS del equipo para un mes
concreto. Visible para los 3 roles (docs/permisos-roles.md § Equipo) — solo
lectura, sin acciones de aprobación (eso es exclusivo de `absences`).

Alcance FIJO al departamento del solicitante: nunca a toda la plantilla ni a
otro departamento. El `department_id` se resuelve SIEMPRE en el backend a
partir del `user_id` del token (`requester_id`) — nunca se acepta como
parámetro del cliente, para que no se pueda pedir el calendario de un
departamento ajeno cambiando un query param."""

from ...domain.entities import TeamAbsenceEntry
from ...domain.ports import ITeamRepository


class GetTeamCalendarUseCase:
    def __init__(self, repository: ITeamRepository):
        self._repository = repository

    async def execute(self, *, requester_id: str, year: int, month: int) -> list[TeamAbsenceEntry]:
        department_id = await self._repository.get_department_id(requester_id)
        if department_id is None:
            # Decisión: un usuario sin departamento asignado no tiene un
            # "equipo" al que pertenezca — devolver toda la plantilla (o
            # a otros usuarios también sin departamento) rompería el
            # alcance "solo mismo departamento" pedido, así que se
            # devuelve una lista vacía en vez de ampliar el filtro.
            return []
        return await self._repository.list_team_absences(
            department_id=department_id, year=year, month=month
        )
