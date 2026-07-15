import pytest

from src.features.absences.application.use_cases.create_absence_type import (
    CreateAbsenceTypeUseCase,
)
from src.features.absences.domain.errors import AbsenceTypeCodeAlreadyExistsError

from .fakes import FakeAbsenceRepository


@pytest.mark.asyncio
async def test_creates_a_new_absence_type():
    repository = FakeAbsenceRepository()
    use_case = CreateAbsenceTypeUseCase(repository)

    absence_type = await use_case.execute(
        code="excedencia",
        name="Excedencia",
        is_paid=False,
        affects_balance=False,
        default_entitled_days=0,
        color="#9CA3AF",
    )

    assert absence_type.code == "excedencia"
    assert absence_type.is_active is True


@pytest.mark.asyncio
async def test_normalizes_the_code_to_lowercase():
    repository = FakeAbsenceRepository()
    use_case = CreateAbsenceTypeUseCase(repository)

    absence_type = await use_case.execute(
        code="  EXCEDENCIA  ",
        name="Excedencia",
        is_paid=False,
        affects_balance=False,
        default_entitled_days=0,
        color=None,
    )

    assert absence_type.code == "excedencia"


@pytest.mark.asyncio
async def test_rejects_a_duplicate_code():
    repository = FakeAbsenceRepository()
    use_case = CreateAbsenceTypeUseCase(repository)
    await use_case.execute(
        code="excedencia",
        name="Excedencia",
        is_paid=False,
        affects_balance=False,
        default_entitled_days=0,
        color=None,
    )

    with pytest.raises(AbsenceTypeCodeAlreadyExistsError):
        await use_case.execute(
            code="excedencia",
            name="Duplicado",
            is_paid=True,
            affects_balance=True,
            default_entitled_days=5,
            color=None,
        )
