from datetime import date

import pytest

from src.features.team.application.use_cases.get_upcoming_birthdays import (
    GetUpcomingBirthdaysUseCase,
)
from src.features.team.domain.entities import TeamBirthday

from .fakes import FakeTeamRepository


@pytest.mark.asyncio
async def test_returns_birthdays_from_repository():
    birthdays = [
        TeamBirthday(
            user_id="user-1",
            full_name="Ana García",
            avatar_url=None,
            day=15,
            month=7,
            is_today=True,
        )
    ]
    use_case = GetUpcomingBirthdaysUseCase(FakeTeamRepository(birthdays=birthdays))

    entries = await use_case.execute(days=7, today=date(2026, 7, 15))

    assert entries == birthdays


@pytest.mark.asyncio
async def test_returns_empty_list_when_no_birthdays_in_window():
    use_case = GetUpcomingBirthdaysUseCase(FakeTeamRepository())

    assert await use_case.execute(days=7, today=date(2026, 7, 15)) == []


@pytest.mark.asyncio
async def test_forwards_days_and_today_to_repository():
    repository = FakeTeamRepository()
    use_case = GetUpcomingBirthdaysUseCase(repository)

    await use_case.execute(days=30, today=date(2026, 12, 29))

    assert repository.received_days == 30
    assert repository.received_today == date(2026, 12, 29)


@pytest.mark.asyncio
async def test_defaults_days_to_seven_and_today_to_current_date():
    repository = FakeTeamRepository()
    use_case = GetUpcomingBirthdaysUseCase(repository)

    await use_case.execute()

    assert repository.received_days == 7
    assert repository.received_today == date.today()
