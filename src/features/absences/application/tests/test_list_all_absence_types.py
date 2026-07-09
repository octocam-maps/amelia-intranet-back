import pytest

from src.features.absences.application.use_cases.create_absence_type import (
    CreateAbsenceTypeUseCase,
)
from src.features.absences.application.use_cases.list_all_absence_types import (
    ListAllAbsenceTypesUseCase,
)
from src.features.absences.application.use_cases.update_absence_type import (
    UpdateAbsenceTypeUseCase,
)

from .fakes import FakeAbsenceRepository


@pytest.mark.asyncio
async def test_includes_deactivated_types_unlike_the_employee_facing_list():
    repository = FakeAbsenceRepository()
    created = await CreateAbsenceTypeUseCase(repository).execute(
        code="excedencia",
        name="Excedencia",
        is_paid=False,
        affects_balance=False,
        default_entitled_days=0,
        color=None,
    )
    await UpdateAbsenceTypeUseCase(repository).execute(created.id, is_active=False)

    types = await ListAllAbsenceTypesUseCase(repository).execute()

    assert len(types) == 1
    assert types[0].is_active is False
