from datetime import date, datetime, timezone

import pytest

from src.features.absences.application.use_cases.create_absence_request import (
    CreateAbsenceRequestUseCase,
)
from src.features.absences.domain.entities import AbsenceBalance, AbsenceRequest, AbsenceType
from src.features.absences.domain.errors import (
    AbsenceRequestOverlapError,
    InsufficientBalanceError,
    InvalidDateRangeError,
)

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
        requester_role="empleado",
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
            requester_role="empleado",
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
        requester_role="empleado",
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
            requester_role="empleado",
            absence_type_id="type-vacaciones",
            start_date=_monday(30),
            end_date=_friday(30),
            reason=None,
        )


@pytest.mark.asyncio
async def test_race_at_reserve_time_raises_insufficient_balance_and_creates_nothing():
    """RACE-1: aunque el saldo en memoria pareciera suficiente, el UPDATE
    atómico (`try_reserve_balance`) es la fuente de verdad — si en el
    momento del commit ya no cubre la solicitud (otra petición concurrente
    se adelantó), se rechaza sin crear la solicitud ni dejar un ajuste a
    medias."""

    class _RaceRepository(FakeAbsenceRepository):
        async def try_reserve_balance(self, *args, **kwargs) -> bool:
            return False

    balance = AbsenceBalance(
        id="balance-1",
        user_id="user-1",
        absence_type_id="type-vacaciones",
        year=2026,
        entitled_days=23,
        used_days=0,
        pending_days=0,
    )
    repository = _RaceRepository(types=[_VACACIONES], balances=[balance])
    use_case = CreateAbsenceRequestUseCase(repository)

    with pytest.raises(InsufficientBalanceError):
        await use_case.execute(
            user_id="user-1",
            requester_role="empleado",
            absence_type_id="type-vacaciones",
            start_date=_monday(30),
            end_date=_friday(30),
            reason=None,
        )

    assert repository.requests == {}


@pytest.mark.asyncio
async def test_type_that_does_not_affect_balance_skips_balance_check():
    """La baja médica no descuenta del saldo (010_absence_types_defaults.sql) —
    no exige balance previo ni lo crea."""
    repository = FakeAbsenceRepository(types=[_BAJA_MEDICA])
    use_case = CreateAbsenceRequestUseCase(repository)

    request = await use_case.execute(
        user_id="user-1",
        requester_role="empleado",
        absence_type_id="type-baja",
        start_date=_monday(30),
        end_date=_friday(30),
        reason="Gripe",
    )

    assert request.days_count == 5.0
    assert repository.balances == {}


@pytest.mark.asyncio
async def test_rejects_a_request_that_overlaps_an_existing_pending_request():
    """Anti-solape (bug real, auditoría QA): sin este chequeo, nada impedía
    crear dos solicitudes `pending`/`approved` del mismo usuario para fechas
    que se pisan."""
    existing = AbsenceRequest(
        id="req-existing",
        user_id="user-1",
        absence_type_id="type-vacaciones",
        start_date=_monday(30),
        end_date=_friday(30),
        days_count=5.0,
        reason=None,
        status="pending",
        reviewed_by=None,
        reviewed_at=None,
        review_note=None,
        created_at=datetime.now(timezone.utc),
    )
    repository = FakeAbsenceRepository(types=[_VACACIONES], requests=[existing])
    use_case = CreateAbsenceRequestUseCase(repository)

    # Solapa a mitad de semana (miércoles a lunes siguiente).
    wednesday = date.fromisocalendar(2026, 30, 3)
    following_monday = date.fromisocalendar(2026, 31, 1)

    with pytest.raises(AbsenceRequestOverlapError):
        await use_case.execute(
            user_id="user-1",
            requester_role="empleado",
            absence_type_id="type-vacaciones",
            start_date=wednesday,
            end_date=following_monday,
            reason=None,
        )


@pytest.mark.asyncio
async def test_does_not_reject_a_request_that_overlaps_someone_elses_request():
    existing = AbsenceRequest(
        id="req-existing",
        user_id="user-2",
        absence_type_id="type-vacaciones",
        start_date=_monday(30),
        end_date=_friday(30),
        days_count=5.0,
        reason=None,
        status="pending",
        reviewed_by=None,
        reviewed_at=None,
        review_note=None,
        created_at=datetime.now(timezone.utc),
    )
    repository = FakeAbsenceRepository(types=[_VACACIONES], requests=[existing])
    use_case = CreateAbsenceRequestUseCase(repository)

    request = await use_case.execute(
        user_id="user-1",
        requester_role="empleado",
        absence_type_id="type-vacaciones",
        start_date=_monday(30),
        end_date=_friday(30),
        reason=None,
    )

    assert request.days_count == 5.0


@pytest.mark.asyncio
async def test_admin_request_is_created_already_approved_and_consumes_used_days():
    """Autoaprobación del administrador (B-1c): su propia solicitud nace en
    `approved` — nunca pasa por la bandeja de pendientes — y descuenta
    `used_days` directamente, no `pending_days` (evita la doble
    contabilidad: reservado Y usado a la vez)."""
    repository = FakeAbsenceRepository(types=[_VACACIONES])
    use_case = CreateAbsenceRequestUseCase(repository)

    request = await use_case.execute(
        user_id="admin-1",
        requester_role="administrador",
        absence_type_id="type-vacaciones",
        start_date=_monday(30),
        end_date=_friday(30),
        reason=None,
    )

    assert request.status == "approved"
    assert request.reviewed_by == "admin-1"
    assert request.reviewed_at is not None

    balance = repository.balances[("admin-1", "type-vacaciones", 2026)]
    assert balance.used_days == 5.0
    assert balance.pending_days == 0.0


@pytest.mark.asyncio
async def test_admin_request_never_reaches_the_pending_tray():
    repository = FakeAbsenceRepository(types=[_VACACIONES])
    use_case = CreateAbsenceRequestUseCase(repository)

    await use_case.execute(
        user_id="admin-1",
        requester_role="administrador",
        absence_type_id="type-vacaciones",
        start_date=_monday(30),
        end_date=_friday(30),
        reason=None,
    )

    assert await repository.list_pending_requests() == []


@pytest.mark.asyncio
async def test_employee_request_still_stays_pending_and_reserves_pending_days():
    """No romper el comportamiento existente: un empleado sigue quedando en
    `pending` con los días reservados en `pending_days`, no en `used_days`."""
    repository = FakeAbsenceRepository(types=[_VACACIONES])
    use_case = CreateAbsenceRequestUseCase(repository)

    request = await use_case.execute(
        user_id="user-1",
        requester_role="empleado",
        absence_type_id="type-vacaciones",
        start_date=_monday(30),
        end_date=_friday(30),
        reason=None,
    )

    assert request.status == "pending"
    assert request.reviewed_by is None

    balance = repository.balances[("user-1", "type-vacaciones", 2026)]
    assert balance.pending_days == 5.0
    assert balance.used_days == 0.0


@pytest.mark.asyncio
async def test_admin_request_still_rejected_when_balance_is_insufficient():
    """La autoaprobación NO se salta las validaciones de negocio — solo el
    paso de revisión manual. Saldo insuficiente sigue rechazando, igual que
    a un empleado."""
    balance = AbsenceBalance(
        id="balance-1",
        user_id="admin-1",
        absence_type_id="type-vacaciones",
        year=2026,
        entitled_days=3,
        used_days=0,
        pending_days=0,
    )
    repository = FakeAbsenceRepository(types=[_VACACIONES], balances=[balance])
    use_case = CreateAbsenceRequestUseCase(repository)

    with pytest.raises(InsufficientBalanceError):
        await use_case.execute(
            user_id="admin-1",
            requester_role="administrador",
            absence_type_id="type-vacaciones",
            start_date=_monday(30),
            end_date=_friday(30),
            reason=None,
        )

    assert repository.requests == {}


@pytest.mark.asyncio
async def test_admin_request_still_rejected_when_it_overlaps_an_existing_request():
    """Idem para el anti-solape — el admin no puede crear dos solicitudes que
    se pisen solo por autoaprobarse."""
    existing = AbsenceRequest(
        id="req-existing",
        user_id="admin-1",
        absence_type_id="type-vacaciones",
        start_date=_monday(30),
        end_date=_friday(30),
        days_count=5.0,
        reason=None,
        status="approved",
        reviewed_by="admin-1",
        reviewed_at=datetime.now(timezone.utc),
        review_note=None,
        created_at=datetime.now(timezone.utc),
    )
    repository = FakeAbsenceRepository(types=[_VACACIONES], requests=[existing])
    use_case = CreateAbsenceRequestUseCase(repository)

    with pytest.raises(AbsenceRequestOverlapError):
        await use_case.execute(
            user_id="admin-1",
            requester_role="administrador",
            absence_type_id="type-vacaciones",
            start_date=_monday(30),
            end_date=_friday(30),
            reason=None,
        )


@pytest.mark.asyncio
async def test_does_not_reject_a_request_that_overlaps_a_rejected_request():
    """Una solicitud `rejected` no bloquea nada — solo `pending`/`approved`."""
    existing = AbsenceRequest(
        id="req-existing",
        user_id="user-1",
        absence_type_id="type-vacaciones",
        start_date=_monday(30),
        end_date=_friday(30),
        days_count=5.0,
        reason=None,
        status="rejected",
        reviewed_by="admin-1",
        reviewed_at=datetime.now(timezone.utc),
        review_note="No hay cobertura",
        created_at=datetime.now(timezone.utc),
    )
    repository = FakeAbsenceRepository(types=[_VACACIONES], requests=[existing])
    use_case = CreateAbsenceRequestUseCase(repository)

    request = await use_case.execute(
        user_id="user-1",
        requester_role="empleado",
        absence_type_id="type-vacaciones",
        start_date=_monday(30),
        end_date=_friday(30),
        reason=None,
    )

    assert request.days_count == 5.0
