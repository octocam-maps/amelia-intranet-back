from datetime import date

import pytest

from src.features.team.application.use_cases.get_vacation_calendar import (
    GetVacationCalendarUseCase,
)
from src.features.team.domain.entities import VacationCalendarEntry

from .fakes import FakeTeamRepository


@pytest.mark.asyncio
async def test_returns_approved_vacations_from_repository():
    vacations = [
        VacationCalendarEntry(
            user_id="user-1",
            full_name="Ana García",
            start_date=date(2026, 7, 20),
            end_date=date(2026, 7, 24),
        )
    ]
    use_case = GetVacationCalendarUseCase(FakeTeamRepository(vacations=vacations))

    entries = await use_case.execute(year=2026, month=7)

    assert entries == vacations


@pytest.mark.asyncio
async def test_returns_empty_list_when_no_vacations_that_month():
    use_case = GetVacationCalendarUseCase(FakeTeamRepository())

    assert await use_case.execute(year=2026, month=7) == []
