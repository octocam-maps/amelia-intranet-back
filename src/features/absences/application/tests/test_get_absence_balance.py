import pytest

from src.features.absences.application.use_cases.get_absence_balance import (
    GetAbsenceBalanceUseCase,
)
from src.features.absences.domain.entities import AbsenceType
from src.features.absences.domain.errors import AbsenceForbiddenError

from .fakes import FakeAbsenceRepository

_VACACIONES = AbsenceType(
    id="type-vacaciones",
    code="vacaciones",
    name="Vacaciones",
    is_paid=True,
    affects_balance=True,
    default_entitled_days=23,
    color="#00D170",
    is_active=True,
)


@pytest.mark.asyncio
async def test_creates_missing_balance_rows_on_first_query():
    repository = FakeAbsenceRepository(types=[_VACACIONES])
    use_case = GetAbsenceBalanceUseCase(repository)

    balances = await use_case.execute(requester_id="user-1", requester_role="empleado", year=2026)

    assert len(balances) == 1
    assert balances[0].entitled_days == 23
    assert balances[0].available_days == 23


@pytest.mark.asyncio
async def test_employee_cannot_query_another_users_balance():
    use_case = GetAbsenceBalanceUseCase(FakeAbsenceRepository(types=[_VACACIONES]))

    with pytest.raises(AbsenceForbiddenError):
        await use_case.execute(
            requester_id="user-1", requester_role="empleado", target_user_id="user-2"
        )


@pytest.mark.asyncio
async def test_admin_can_query_another_users_balance():
    repository = FakeAbsenceRepository(types=[_VACACIONES])
    use_case = GetAbsenceBalanceUseCase(repository)

    balances = await use_case.execute(
        requester_id="admin-1",
        requester_role="administrador",
        target_user_id="user-2",
        year=2026,
    )

    assert balances[0].entitled_days == 23
