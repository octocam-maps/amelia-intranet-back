from datetime import date, datetime, timezone

import pytest

from src.features.absences.application.use_cases.review_absence_request import (
    ReviewAbsenceRequestUseCase,
)
from src.features.absences.domain.entities import AbsenceBalance, AbsenceRequest, AbsenceType
from src.features.absences.domain.errors import AbsenceRequestAlreadyReviewedError

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


def _pending_request() -> AbsenceRequest:
    return AbsenceRequest(
        id="req-1",
        user_id="user-1",
        absence_type_id="type-vacaciones",
        start_date=date(2026, 7, 6),
        end_date=date(2026, 7, 10),
        days_count=5,
        reason=None,
        status="pending",
        reviewed_by=None,
        reviewed_at=None,
        review_note=None,
        created_at=datetime.now(timezone.utc),
    )


def _balance() -> AbsenceBalance:
    return AbsenceBalance(
        id="balance-1",
        user_id="user-1",
        absence_type_id="type-vacaciones",
        year=2026,
        entitled_days=23,
        used_days=0,
        pending_days=5,
    )


@pytest.mark.asyncio
async def test_approve_moves_days_from_pending_to_used():
    repository = FakeAbsenceRepository(
        types=[_VACACIONES], requests=[_pending_request()], balances=[_balance()]
    )
    use_case = ReviewAbsenceRequestUseCase(repository)

    request = await use_case.execute(
        request_id="req-1", reviewer_id="admin-1", decision="approved", note="OK"
    )

    assert request.status == "approved"
    updated_balance = repository.balances[("user-1", "type-vacaciones", 2026)]
    assert updated_balance.used_days == 5
    assert updated_balance.pending_days == 0


@pytest.mark.asyncio
async def test_reject_clears_pending_without_touching_used():
    repository = FakeAbsenceRepository(
        types=[_VACACIONES], requests=[_pending_request()], balances=[_balance()]
    )
    use_case = ReviewAbsenceRequestUseCase(repository)

    request = await use_case.execute(
        request_id="req-1",
        reviewer_id="admin-1",
        decision="rejected",
        note="Sin cobertura de equipo esa semana",
    )

    assert request.status == "rejected"
    updated_balance = repository.balances[("user-1", "type-vacaciones", 2026)]
    assert updated_balance.used_days == 0
    assert updated_balance.pending_days == 0


@pytest.mark.asyncio
async def test_race_at_review_time_raises_already_reviewed_without_double_adjusting_balance():
    """RACE-2: aunque `request.status` en memoria diga "pending", el
    UPDATE...WHERE status='pending' es la fuente de verdad — si otra
    revisión concurrente ya lo cambió (0 filas afectadas), se rechaza SIN
    tocar el saldo una segunda vez."""

    class _RaceRepository(FakeAbsenceRepository):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.adjust_balance_calls = 0

        async def update_request_status_if_pending(self, *args, **kwargs):
            return None

        async def adjust_balance(self, *args, **kwargs):
            self.adjust_balance_calls += 1
            await super().adjust_balance(*args, **kwargs)

    repository = _RaceRepository(
        types=[_VACACIONES], requests=[_pending_request()], balances=[_balance()]
    )
    use_case = ReviewAbsenceRequestUseCase(repository)

    with pytest.raises(AbsenceRequestAlreadyReviewedError):
        await use_case.execute(
            request_id="req-1", reviewer_id="admin-1", decision="approved", note=None
        )

    assert repository.adjust_balance_calls == 0


@pytest.mark.asyncio
async def test_cannot_review_twice():
    repository = FakeAbsenceRepository(
        types=[_VACACIONES], requests=[_pending_request()], balances=[_balance()]
    )
    use_case = ReviewAbsenceRequestUseCase(repository)
    await use_case.execute(request_id="req-1", reviewer_id="admin-1", decision="approved", note=None)

    with pytest.raises(AbsenceRequestAlreadyReviewedError):
        await use_case.execute(
            request_id="req-1", reviewer_id="admin-1", decision="rejected", note=None
        )
