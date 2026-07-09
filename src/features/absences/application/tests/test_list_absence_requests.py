from datetime import date, datetime, timezone

import pytest

from src.features.absences.application.use_cases.list_absence_requests import (
    ListAbsenceRequestsUseCase,
)
from src.features.absences.domain.entities import AbsenceRequest
from src.features.absences.domain.errors import AbsenceForbiddenError

from .fakes import FakeAbsenceRepository


def _request(request_id: str, user_id: str) -> AbsenceRequest:
    return AbsenceRequest(
        id=request_id,
        user_id=user_id,
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


@pytest.mark.asyncio
async def test_employee_only_sees_their_own_requests():
    repository = FakeAbsenceRepository(requests=[_request("r1", "user-1"), _request("r2", "user-2")])
    use_case = ListAbsenceRequestsUseCase(repository)

    requests = await use_case.execute(requester_id="user-1", requester_role="empleado")

    assert [r.id for r in requests] == ["r1"]


@pytest.mark.asyncio
async def test_employee_cannot_open_pending_tray():
    use_case = ListAbsenceRequestsUseCase(FakeAbsenceRepository())

    with pytest.raises(AbsenceForbiddenError):
        await use_case.execute(requester_id="user-1", requester_role="empleado", mode="pending")


@pytest.mark.asyncio
async def test_employee_cannot_query_another_users_requests():
    use_case = ListAbsenceRequestsUseCase(FakeAbsenceRepository())

    with pytest.raises(AbsenceForbiddenError):
        await use_case.execute(
            requester_id="user-1", requester_role="empleado", target_user_id="user-2"
        )


@pytest.mark.asyncio
async def test_admin_sees_pending_tray_across_users():
    repository = FakeAbsenceRepository(requests=[_request("r1", "user-1"), _request("r2", "user-2")])
    use_case = ListAbsenceRequestsUseCase(repository)

    requests = await use_case.execute(
        requester_id="admin-1", requester_role="administrador", mode="pending"
    )

    assert {r.id for r in requests} == {"r1", "r2"}
