from datetime import date

import pytest

from src.features.holidays.application.use_cases.create_holiday import CreateHolidayUseCase
from src.features.holidays.domain.errors import HolidayAlreadyExistsError, InvalidEntityCodeError

from .fakes import FakeHolidayRepository


@pytest.mark.asyncio
async def test_creates_a_holiday_that_applies_to_every_entity_by_default():
    repository = FakeHolidayRepository()
    use_case = CreateHolidayUseCase(repository)

    holiday = await use_case.execute(day=date(2026, 12, 25), name="Navidad", entity_code=None)

    assert holiday.entity_id is None


@pytest.mark.asyncio
async def test_creates_a_holiday_scoped_to_one_entity():
    repository = FakeHolidayRepository()
    use_case = CreateHolidayUseCase(repository)

    holiday = await use_case.execute(
        day=date(2026, 9, 24), name="La Mercè", entity_code="hub"
    )

    assert holiday.entity_code == "hub"


@pytest.mark.asyncio
async def test_rejects_an_unknown_entity_code():
    repository = FakeHolidayRepository()
    use_case = CreateHolidayUseCase(repository)

    with pytest.raises(InvalidEntityCodeError):
        await use_case.execute(day=date(2026, 1, 1), name="X", entity_code="does-not-exist")


@pytest.mark.asyncio
async def test_rejects_a_duplicate_day_for_the_same_scope():
    repository = FakeHolidayRepository()
    use_case = CreateHolidayUseCase(repository)
    await use_case.execute(day=date(2026, 1, 1), name="Año Nuevo", entity_code=None)

    with pytest.raises(HolidayAlreadyExistsError):
        await use_case.execute(day=date(2026, 1, 1), name="Duplicado", entity_code=None)
