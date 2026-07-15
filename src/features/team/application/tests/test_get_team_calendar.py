from datetime import date

import pytest

from src.features.team.application.use_cases.get_team_calendar import (
    GetTeamCalendarUseCase,
)
from src.features.team.domain.entities import TeamAbsenceEntry

from .fakes import FakeTeamRepository


@pytest.mark.asyncio
async def test_returns_absences_from_repository_scoped_to_requesters_department():
    absences = [
        TeamAbsenceEntry(
            user_id="user-1",
            full_name="Ana García",
            start_date=date(2026, 7, 20),
            end_date=date(2026, 7, 24),
            kind="vacaciones",
        )
    ]
    repository = FakeTeamRepository(absences=absences, department_id="dept-1")
    use_case = GetTeamCalendarUseCase(repository)

    entries = await use_case.execute(requester_id="user-1", year=2026, month=7)

    assert entries == absences
    assert repository.received_department_id_lookup_for == "user-1"
    assert repository.received_list_absences_args == {
        "department_id": "dept-1",
        "year": 2026,
        "month": 7,
    }


@pytest.mark.asyncio
async def test_returns_empty_list_when_no_absences_that_month():
    use_case = GetTeamCalendarUseCase(FakeTeamRepository(department_id="dept-1"))

    assert await use_case.execute(requester_id="user-1", year=2026, month=7) == []


@pytest.mark.asyncio
async def test_returns_empty_list_when_requester_has_no_department():
    """Decisión de producto: sin departamento asignado no hay "equipo" al
    que pertenezca el solicitante — no se amplía el alcance a toda la
    plantilla ni a otros usuarios sin departamento."""
    repository = FakeTeamRepository(department_id=None)
    use_case = GetTeamCalendarUseCase(repository)

    entries = await use_case.execute(requester_id="user-without-department", year=2026, month=7)

    assert entries == []
    assert repository.received_list_absences_args is None
