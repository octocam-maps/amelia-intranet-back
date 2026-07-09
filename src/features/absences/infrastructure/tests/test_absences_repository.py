"""
Regresión: `/absences/requests/pending` y `/requests/all` deben devolver
`user_full_name` (JOIN con `users`) para que la bandeja de aprobación y el
gantt "Calendario de la plantilla" muestren el nombre real en vez de
"Empleado #XXXX". Mismo patrón de mock de pool que
`features/time_clock/infrastructure/tests/test_time_clock_repository.py`.
"""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.features.absences.infrastructure.repositories.absence_repository import (
    PostgresAbsenceRepository,
)


def _row(**overrides) -> dict:
    row = {
        "id": "req-1",
        "user_id": "user-1",
        "absence_type_id": "type-vacaciones",
        "start_date": date(2026, 7, 20),
        "end_date": date(2026, 7, 24),
        "days_count": 5,
        "reason": None,
        "status": "pending",
        "reviewed_by": None,
        "reviewed_at": None,
        "review_note": None,
        "created_at": datetime.now(timezone.utc),
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_list_pending_requests_enriches_with_user_full_name():
    pool = AsyncMock()
    pool.fetch.return_value = [_row(user_full_name="Ana García")]
    repository = PostgresAbsenceRepository(pool)

    requests = await repository.list_pending_requests()

    assert requests[0].user_full_name == "Ana García"
    query = pool.fetch.call_args[0][0]
    assert "JOIN users" in query
    assert "status = 'pending'" in query


@pytest.mark.asyncio
async def test_list_all_requests_enriches_with_user_full_name():
    pool = AsyncMock()
    pool.fetch.return_value = [_row(user_full_name="Ana García")]
    repository = PostgresAbsenceRepository(pool)

    requests = await repository.list_all_requests()

    assert requests[0].user_full_name == "Ana García"
    assert "JOIN users" in pool.fetch.call_args[0][0]


@pytest.mark.asyncio
async def test_list_requests_for_user_leaves_user_full_name_none():
    """`SELECT *` sin JOIN — sin `user_full_name` en la fila, no debe reventar."""
    pool = AsyncMock()
    pool.fetch.return_value = [_row()]
    repository = PostgresAbsenceRepository(pool)

    requests = await repository.list_requests_for_user("user-1")

    assert requests[0].user_full_name is None
