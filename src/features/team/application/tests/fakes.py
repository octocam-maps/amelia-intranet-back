"""Fake en memoria de `ITeamRepository` — permite testear los casos de uso
sin Postgres."""

from datetime import date
from typing import Optional

from src.features.team.domain.entities import TeamAbsenceEntry, TeamBirthday, TeamMember


class FakeTeamRepository:
    def __init__(
        self,
        members: Optional[list[TeamMember]] = None,
        absences: Optional[list[TeamAbsenceEntry]] = None,
        birthdays: Optional[list[TeamBirthday]] = None,
        department_id: Optional[str] = "dept-1",
    ):
        self.members = members or []
        self.absences = absences or []
        self.birthdays = birthdays or []
        self.department_id = department_id
        self.received_today: Optional[date] = None
        self.received_days: Optional[int] = None
        self.received_department_id_lookup_for: Optional[str] = None
        self.received_list_absences_args: Optional[dict] = None

    async def list_directory(self) -> list[TeamMember]:
        return self.members

    async def get_department_id(self, user_id: str) -> Optional[str]:
        self.received_department_id_lookup_for = user_id
        return self.department_id

    async def list_team_absences(
        self, *, department_id: str, year: int, month: int
    ) -> list[TeamAbsenceEntry]:
        self.received_list_absences_args = {
            "department_id": department_id,
            "year": year,
            "month": month,
        }
        return self.absences

    async def list_upcoming_birthdays(self, *, today: date, days: int) -> list[TeamBirthday]:
        self.received_today = today
        self.received_days = days
        return self.birthdays
