"""Cableado del disparador `absence_requested` — al crear una solicitud se
notifica a la bandeja del admin (docs/requerimientos-amelia-intranet.pdf
§6). `NotifyUseCase.notify_admins` en sí ya tiene su propia suite en
`features/notifications`; aquí solo se verifica que
`CreateAbsenceRequestUseCase` la invoca."""

from datetime import date

import pytest

from src.features.absences.application.use_cases.create_absence_request import (
    CreateAbsenceRequestUseCase,
)
from src.features.absences.domain.entities import AbsenceType

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
        self.admin_calls: list[dict] = []

    async def notify_admins(self, **kwargs):
        self.admin_calls.append(kwargs)


def _monday(week: int) -> date:
    return date.fromisocalendar(2026, week, 1)


def _friday(week: int) -> date:
    return date.fromisocalendar(2026, week, 5)


@pytest.mark.asyncio
async def test_creating_a_request_notifies_the_admin_tray():
    repository = FakeAbsenceRepository(types=[_VACACIONES])
    notify = _RecordingNotify()
    use_case = CreateAbsenceRequestUseCase(repository, notify)

    await use_case.execute(
        user_id="user-1",
        absence_type_id="type-vacaciones",
        start_date=_monday(30),
        end_date=_friday(30),
        reason=None,
    )

    assert len(notify.admin_calls) == 1
    assert notify.admin_calls[0]["type"] == "absence_requested"


@pytest.mark.asyncio
async def test_create_without_a_notify_dependency_still_works():
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
