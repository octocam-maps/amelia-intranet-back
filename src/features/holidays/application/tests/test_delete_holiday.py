from datetime import date

import pytest

from src.features.holidays.application.use_cases.create_holiday import CreateHolidayUseCase
from src.features.holidays.application.use_cases.delete_holiday import DeleteHolidayUseCase
from src.features.holidays.domain.errors import HolidayNotFoundError

from .fakes import FakeHolidayRepository


@pytest.mark.asyncio
async def test_deletes_an_existing_holiday():
    repository = FakeHolidayRepository()
    created = await CreateHolidayUseCase(repository).execute(
        day=date(2026, 1, 1), name="Año Nuevo", entity_code=None
    )
    use_case = DeleteHolidayUseCase(repository)

    await use_case.execute(created.id)

    assert await repository.find_by_id(created.id) is None


@pytest.mark.asyncio
async def test_raises_not_found_for_an_unknown_holiday():
    repository = FakeHolidayRepository()
    use_case = DeleteHolidayUseCase(repository)

    with pytest.raises(HolidayNotFoundError):
        await use_case.execute("does-not-exist")
