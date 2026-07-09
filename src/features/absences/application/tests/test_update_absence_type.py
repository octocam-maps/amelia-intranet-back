import pytest

from src.features.absences.application.use_cases.create_absence_type import (
    CreateAbsenceTypeUseCase,
)
from src.features.absences.application.use_cases.update_absence_type import (
    UpdateAbsenceTypeUseCase,
)
from src.features.absences.domain.errors import AbsenceTypeNotFoundError

from .fakes import FakeAbsenceRepository


@pytest.mark.asyncio
async def test_updates_only_the_fields_that_are_informed():
    repository = FakeAbsenceRepository()
    created = await CreateAbsenceTypeUseCase(repository).execute(
        code="excedencia",
        name="Excedencia",
        is_paid=False,
        affects_balance=False,
        default_entitled_days=0,
        color=None,
    )
    use_case = UpdateAbsenceTypeUseCase(repository)

    updated = await use_case.execute(created.id, default_entitled_days=10)

    assert updated.default_entitled_days == 10
    assert updated.name == "Excedencia"


@pytest.mark.asyncio
async def test_deactivating_a_type_does_not_delete_it():
    repository = FakeAbsenceRepository()
    created = await CreateAbsenceTypeUseCase(repository).execute(
        code="excedencia",
        name="Excedencia",
        is_paid=False,
        affects_balance=False,
        default_entitled_days=0,
        color=None,
    )
    use_case = UpdateAbsenceTypeUseCase(repository)

    updated = await use_case.execute(created.id, is_active=False)

    assert updated.is_active is False
    assert await repository.find_type_by_id(created.id) is not None


@pytest.mark.asyncio
async def test_raises_not_found_for_an_unknown_type():
    repository = FakeAbsenceRepository()
    use_case = UpdateAbsenceTypeUseCase(repository)

    with pytest.raises(AbsenceTypeNotFoundError):
        await use_case.execute("does-not-exist", name="x")
