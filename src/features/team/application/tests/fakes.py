"""Fake en memoria de `ITeamRepository` — permite testear los casos de uso
sin Postgres."""

from datetime import date
from typing import Optional

from src.features.team.domain.entities import TeamBirthday, TeamMember, VacationCalendarEntry


class FakeTeamRepository:
    def __init__(
        self,
        members: Optional[list[TeamMember]] = None,
        vacations: Optional[list[VacationCalendarEntry]] = None,
        birthdays: Optional[list[TeamBirthday]] = None,
    ):
        self.members = members or []
        self.vacations = vacations or []
        self.birthdays = birthdays or []
        self.received_today: Optional[date] = None
        self.received_days: Optional[int] = None

    async def list_directory(self) -> list[TeamMember]:
        return self.members

    async def list_approved_vacations(self, year: int, month: int) -> list[VacationCalendarEntry]:
        return self.vacations

    async def list_upcoming_birthdays(self, *, today: date, days: int) -> list[TeamBirthday]:
        self.received_today = today
        self.received_days = days
        return self.birthdays
