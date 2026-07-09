from datetime import date

import pytest

from src.features.absences.application.use_cases.create_absence_request import (
    CreateAbsenceRequestUseCase,
)
from src.features.absences.domain.entities import AbsenceBalance, AbsenceType
from src.features.absences.domain.errors import InsufficientBalanceError, InvalidDateRangeError

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
_BAJA_MEDICA = AbsenceType(
    id="type-baja",
    code="baja_medica",
    name="Baja médica",
    is_paid=True,
    affects_balance=False,
    default_entitled_days=0,
    color="#3C83F6",
    is_active=True,
)


def _monday(week: int) -> date:
    """`date.fromisocalendar` garantiza el día de la semana sin calcularlo a mano."""
    return date.fromisocalendar(2026, week, 1)


def _friday(week: int) -> date:
    return date.fromisocalendar(2026, week, 5)


@pytest.mark.asyncio
async def test_counts_only_business_days_mon_to_fri():
    repository = FakeAbsenceRepository(types=[_VACACIONES])
    use_case = CreateAbsenceRequestUseCase(repository)

    request = await use_case.execute(
        user_id="user-1",
        absence_type_id="type-vacaciones",
        start_date=_monday(30),
        end_date=_friday(30),
        reason=None,
    )

    assert request.days_count == 5.0


@pytest.mark.asyncio
async def test_rejects_range_with_zero_business_days():
    repository = FakeAbsenceRepository(types=[_VACACIONES])
    use_case = CreateAbsenceRequestUseCase(repository)
    saturday = date.fromisocalendar(2026, 30, 6)
    sunday = date.fromisocalendar(2026, 30, 7)

    with pytest.raises(InvalidDateRangeError):
        await use_case.execute(
            user_id="user-1",
            absence_type_id="type-vacaciones",
            start_date=saturday,
            end_date=sunday,
            reason=None,
        )


@pytest.mark.asyncio
async def test_excludes_holidays_from_count():
    wednesday = date.fromisocalendar(2026, 30, 3)
    repository = FakeAbsenceRepository(types=[_VACACIONES], holidays=[wednesday])
    use_case = CreateAbsenceRequestUseCase(repository)

    request = await use_case.execute(
        user_id="user-1",
        absence_type_id="type-vacaciones",
        start_date=_monday(30),
        end_date=_friday(30),
        reason=None,
    )

    assert request.days_count == 4.0


@pytest.mark.asyncio
async def test_rejects_when_balance_is_insufficient():
    balance = AbsenceBalance(
        id="balance-1",
        user_id="user-1",
        absence_type_id="type-vacaciones",
        year=2026,
        entitled_days=3,
        used_days=0,
        pending_days=0,
    )
    repository = FakeAbsenceRepository(types=[_VACACIONES], balances=[balance])
    use_case = CreateAbsenceRequestUseCase(repository)

    # Lunes a viernes = 5 días laborables, pero solo hay 3 disponibles.
    with pytest.raises(InsufficientBalanceError):
        await use_case.execute(
            user_id="user-1",
            absence_type_id="type-vacaciones",
            start_date=_monday(30),
            end_date=_friday(30),
            reason=None,
        )


@pytest.mark.asyncio
async def test_type_that_does_not_affect_balance_skips_balance_check():
    """La baja médica no descuenta del saldo (010_absence_types_defaults.sql) —
    no exige balance previo ni lo crea."""
    repository = FakeAbsenceRepository(types=[_BAJA_MEDICA])
    use_case = CreateAbsenceRequestUseCase(repository)

    request = await use_case.execute(
        user_id="user-1",
        absence_type_id="type-baja",
        start_date=_monday(30),
        end_date=_friday(30),
        reason="Gripe",
    )

    assert request.days_count == 5.0
    assert repository.balances == {}
