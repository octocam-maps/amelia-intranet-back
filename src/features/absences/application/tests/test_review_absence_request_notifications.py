"""Cableado del disparador `absence_approved`/`absence_rejected` — el
trabajador dueño de la solicitud es el único destinatario (docs/
requerimientos-amelia-intranet.pdf §6). `NotifyUseCase` en sí ya tiene su
propia suite en `features/notifications`; aquí solo se verifica que
`ReviewAbsenceRequestUseCase` lo invoca con los parámetros correctos."""

from datetime import date, datetime, timezone

import pytest

from src.features.absences.application.use_cases.review_absence_request import (
    ReviewAbsenceRequestUseCase,
)
from src.features.absences.domain.entities import AbsenceBalance, AbsenceRequest, AbsenceType

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


class _RecordingNotify:
    def __init__(self):
        self.calls: list[dict] = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)


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
async def test_approving_notifies_only_the_requesting_worker():
    repository = FakeAbsenceRepository(
        types=[_VACACIONES], requests=[_pending_request()], balances=[_balance()]
    )
    notify = _RecordingNotify()
    use_case = ReviewAbsenceRequestUseCase(repository, notify)

    await use_case.execute(request_id="req-1", reviewer_id="admin-1", decision="approved", note="OK")

    assert len(notify.calls) == 1
    call = notify.calls[0]
    assert call["recipient_ids"] == ["user-1"]
    assert call["type"] == "absence_approved"


@pytest.mark.asyncio
async def test_rejecting_notifies_only_the_requesting_worker():
    repository = FakeAbsenceRepository(
        types=[_VACACIONES], requests=[_pending_request()], balances=[_balance()]
    )
    notify = _RecordingNotify()
    use_case = ReviewAbsenceRequestUseCase(repository, notify)

    await use_case.execute(
        request_id="req-1", reviewer_id="admin-1", decision="rejected", note="Sin cobertura"
    )

    assert len(notify.calls) == 1
    call = notify.calls[0]
    assert call["recipient_ids"] == ["user-1"]
    assert call["type"] == "absence_rejected"


@pytest.mark.asyncio
async def test_review_without_a_notify_dependency_still_works():
    """`notify=None` (default) — el disparador es opcional, no rompe el
    caso de uso si nadie lo inyecta (p. ej. tests que ya existían antes de
    Fase 6)."""
    repository = FakeAbsenceRepository(
        types=[_VACACIONES], requests=[_pending_request()], balances=[_balance()]
    )
    use_case = ReviewAbsenceRequestUseCase(repository)

    request = await use_case.execute(
        request_id="req-1", reviewer_id="admin-1", decision="approved", note=None
    )

    assert request.status == "approved"
