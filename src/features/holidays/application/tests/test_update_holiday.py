from datetime import date

import pytest

from src.features.holidays.application.use_cases.create_holiday import CreateHolidayUseCase
from src.features.holidays.application.use_cases.update_holiday import UpdateHolidayUseCase
from src.features.holidays.domain.errors import HolidayAlreadyExistsError, HolidayNotFoundError

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


@pytest.mark.asyncio
async def test_update_raises_conflict_when_the_new_date_collides_with_another_holiday():
    """Bug real (auditoría QA): `create_holiday` valida duplicados de
    (day, entity_id) pero `update_holiday` no lo hacía — mover un festivo a
    una fecha ya ocupada por otro caía en un 500 de Postgres en vez de un
    409 legible."""
    repository = FakeHolidayRepository()
    await CreateHolidayUseCase(repository).execute(
        day=date(2026, 1, 1), name="Año Nuevo", entity_code=None
    )
    reyes = await CreateHolidayUseCase(repository).execute(
        day=date(2026, 1, 6), name="Reyes", entity_code=None
    )
    use_case = UpdateHolidayUseCase(repository)

    with pytest.raises(HolidayAlreadyExistsError):
        await use_case.execute(reyes.id, day=date(2026, 1, 1))


@pytest.mark.asyncio
async def test_update_does_not_raise_when_colliding_only_with_itself():
    """Editar SOLO el nombre (sin tocar fecha/ámbito) no debe dispararse
    contra su propia fila como si fuera un duplicado."""
    repository = FakeHolidayRepository()
    created = await CreateHolidayUseCase(repository).execute(
        day=date(2026, 1, 1), name="Año Nuevo", entity_code=None
    )
    use_case = UpdateHolidayUseCase(repository)

    updated = await use_case.execute(created.id, day=date(2026, 1, 1), name="Año Nuevo (ES)")

    assert updated.name == "Año Nuevo (ES)"
