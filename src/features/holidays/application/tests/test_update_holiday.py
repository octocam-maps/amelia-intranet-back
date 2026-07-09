from datetime import date

import pytest

from src.features.holidays.application.use_cases.create_holiday import CreateHolidayUseCase
from src.features.holidays.application.use_cases.update_holiday import UpdateHolidayUseCase
from src.features.holidays.domain.errors import HolidayNotFoundError

from .fakes import FakeHolidayRepository


@pytest.mark.asyncio
async def test_updates_only_the_fields_that_are_informed():
    repository = FakeHolidayRepository()
    created = await CreateHolidayUseCase(repository).execute(
        day=date(2026, 1, 1), name="Año Nuevo", entity_code=None
    )
    use_case = UpdateHolidayUseCase(repository)

    updated = await use_case.execute(created.id, name="Año Nuevo (festivo nacional)")

    assert updated.name == "Año Nuevo (festivo nacional)"
    assert updated.day == date(2026, 1, 1)


@pytest.mark.asyncio
async def test_not_passing_entity_code_leaves_the_scope_untouched():
    repository = FakeHolidayRepository()
    created = await CreateHolidayUseCase(repository).execute(
        day=date(2026, 9, 24), name="La Mercè", entity_code="hub"
    )
    use_case = UpdateHolidayUseCase(repository)

    updated = await use_case.execute(created.id, name="La Mercè (festivo local)")

    assert updated.entity_code == "hub"


@pytest.mark.asyncio
async def test_passing_entity_code_none_explicitly_clears_the_scope():
    repository = FakeHolidayRepository()
    created = await CreateHolidayUseCase(repository).execute(
        day=date(2026, 9, 24), name="La Mercè", entity_code="hub"
    )
    use_case = UpdateHolidayUseCase(repository)

    updated = await use_case.execute(created.id, entity_code=None)

    assert updated.entity_id is None


@pytest.mark.asyncio
async def test_raises_not_found_for_an_unknown_holiday():
    repository = FakeHolidayRepository()
    use_case = UpdateHolidayUseCase(repository)

    with pytest.raises(HolidayNotFoundError):
        await use_case.execute("does-not-exist", name="x")
