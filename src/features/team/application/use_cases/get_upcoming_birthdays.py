"""Caso de uso: cumpleaños de la plantilla interna dentro de una ventana de
días (widget "Cumpleaños esta semana" del Inicio — docs/brief-diseno.md C0).
Visible para los 3 roles (docs/permisos-roles.md § Equipo) — solo lectura."""

from datetime import date
from typing import Optional

from ...domain.entities import TeamBirthday
from ...domain.ports import ITeamRepository


class GetUpcomingBirthdaysUseCase:
    def __init__(self, repository: ITeamRepository):
        self._repository = repository

    async def execute(self, *, days: int = 7, today: Optional[date] = None) -> list[TeamBirthday]:
        return await self._repository.list_upcoming_birthdays(today=today or date.today(), days=days)
