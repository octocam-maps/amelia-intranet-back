"""
Descanso por horas extra del técnico (requerimiento v1.2 §M1).

`descanso_horas_extra` tiene `affects_balance = FALSE` —para no descontar del
saldo de vacaciones— y eso significa que la validación de saldo del resto de
tipos NO le aplica. Sin el guard que se prueba aquí, se podrían pedir 40 días
de descanso habiendo hecho 2 horas extra.
"""

import pytest

from src.features.absences.application.use_cases.create_absence_request import (
    MINUTES_PER_COMPENSATION_DAY,
    CreateAbsenceRequestUseCase,
)
from src.features.absences.domain.entities import AbsenceType
from src.features.absences.domain.errors import InsufficientCompensationBalanceError
from src.features.time_clock.domain.policy import (
    MINUTES_PER_COMPENSATION_DAY as TIME_CLOCK_MINUTES_PER_DAY,
)
from src.shared.auth.roles import RoleCode

from .fakes import FakeAbsenceRepository
from .test_create_absence_request import _friday, _monday

_DESCANSO = AbsenceType(
    id="type-descanso",
    code="descanso_horas_extra",
    name="Descanso por horas extra",
    is_paid=True,
    affects_balance=False,
    default_entitled_days=0,
    color="#78716C",
    is_active=True,
)


class _FakeCompensationBalance:
    def __init__(self, available: int):
        self.available = available
        self.calls: list[tuple[str, int]] = []

    async def available_minutes(self, user_id: str, year: int) -> int:
        self.calls.append((user_id, year))
        return self.available


def _use_case(available_minutes: int | None) -> CreateAbsenceRequestUseCase:
    provider = None if available_minutes is None else _FakeCompensationBalance(available_minutes)
    return CreateAbsenceRequestUseCase(
        FakeAbsenceRepository(types=[_DESCANSO]),
        None,
        provider,
    )


def test_the_two_features_agree_on_how_long_a_compensation_day_is():
    """La constante está duplicada a propósito (no acoplar `absences` al
    dominio de `time_clock`). Este test es el que hace que la duplicación sea
    segura: si alguien cambia una, aquí salta."""
    assert MINUTES_PER_COMPENSATION_DAY == TIME_CLOCK_MINUTES_PER_DAY


@pytest.mark.asyncio
async def test_a_request_within_the_accrued_balance_is_accepted():
    # Lunes a martes = 2 días hábiles = 960 min. Saldo justo.
    use_case = _use_case(2 * MINUTES_PER_COMPENSATION_DAY)

    request = await use_case.execute(
        user_id="u-tecnico",
        requester_role=RoleCode.TECNICO,
        absence_type_id=_DESCANSO.id,
        start_date=_monday(20),
        end_date=_monday(20).replace(day=_monday(20).day + 1),
        reason=None,
    )

    assert request.status == "pending"


@pytest.mark.asyncio
async def test_a_request_beyond_the_accrued_balance_is_rejected():
    """El escenario que motivó el guard: 6 horas devengadas, una semana
    pedida."""
    use_case = _use_case(360)  # 6 h

    with pytest.raises(InsufficientCompensationBalanceError, match="6h 00m"):
        await use_case.execute(
            user_id="u-tecnico",
            requester_role=RoleCode.TECNICO,
            absence_type_id=_DESCANSO.id,
            start_date=_monday(20),
            end_date=_friday(20),
            reason=None,
        )


@pytest.mark.asyncio
async def test_a_missing_provider_denies_instead_of_letting_it_through():
    """Fallo de wiring: se deniega. La política contraria produciría descansos
    sin respaldo que nadie detectaría hasta el recuento anual."""
    use_case = _use_case(None)

    with pytest.raises(InsufficientCompensationBalanceError):
        await use_case.execute(
            user_id="u-tecnico",
            requester_role=RoleCode.TECNICO,
            absence_type_id=_DESCANSO.id,
            start_date=_monday(20),
            end_date=_monday(20),
            reason=None,
        )


@pytest.mark.asyncio
async def test_the_balance_is_checked_against_the_year_of_the_start_date():
    """El saldo es ANUAL: pedir en enero con cargo al año anterior sería otra
    contabilidad."""
    provider = _FakeCompensationBalance(10 * MINUTES_PER_COMPENSATION_DAY)
    use_case = CreateAbsenceRequestUseCase(
        FakeAbsenceRepository(types=[_DESCANSO]), None, provider
    )

    await use_case.execute(
        user_id="u-tecnico",
        requester_role=RoleCode.TECNICO,
        absence_type_id=_DESCANSO.id,
        start_date=_monday(20),
        end_date=_monday(20),
        reason=None,
    )

    assert provider.calls == [("u-tecnico", 2026)]
