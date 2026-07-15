"""Fake en memoria de `ITeamRepository` — permite testear los casos de uso
sin Postgres."""

from typing import Optional

from src.features.team.domain.entities import TeamMember, VacationCalendarEntry


class FakeTeamRepository:
    def __init__(
        self,
        members: Optional[list[TeamMember]] = None,
        vacations: Optional[list[VacationCalendarEntry]] = None,
    ):
        self.members = members or []
        self.vacations = vacations or []

    async def list_directory(self) -> list[TeamMember]:
        return self.members

    async def list_approved_vacations(self, year: int, month: int) -> list[VacationCalendarEntry]:
        return self.vacations
