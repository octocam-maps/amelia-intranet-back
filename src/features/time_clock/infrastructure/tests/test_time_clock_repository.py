"""
RACE-3 (auditoría QA Fase 3): `find_overlapping_entry` en el use case es un
check-then-act — el constraint `EXCLUDE` de la migración 012 es la fuente de
verdad real bajo concurrencia. No podemos reproducir la carrera contra un
Postgres real en un test unitario, pero sí la rama de manejo del error: si
asyncpg levanta `ExclusionViolationError`, el repositorio debe traducirlo al
error de dominio `TimeClockOverlapError`.
"""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import asyncpg
import pytest

from src.features.time_clock.domain.errors import TimeClockOverlapError
from src.features.time_clock.infrastructure.repositories.time_clock_repository import (
    PostgresTimeClockRepository,
)


def _fake_pool_raising(exc: Exception) -> AsyncMock:
    pool = AsyncMock()
    pool.fetchrow.side_effect = exc
    return pool


@pytest.mark.asyncio
async def test_create_entry_translates_exclusion_violation_to_overlap_error():
    pool = _fake_pool_raising(asyncpg.exceptions.ExclusionViolationError("overlap"))
    repository = PostgresTimeClockRepository(pool)

    with pytest.raises(TimeClockOverlapError):
        await repository.create_entry(
            user_id="user-1",
            work_date=date(2026, 7, 6),
            clock_in=datetime(2026, 7, 6, 9, 0, tzinfo=timezone.utc),
            clock_out=None,
            source="web",
        )


@pytest.mark.asyncio
async def test_update_entry_translates_exclusion_violation_to_overlap_error():
    pool = _fake_pool_raising(asyncpg.exceptions.ExclusionViolationError("overlap"))
    repository = PostgresTimeClockRepository(pool)

    with pytest.raises(TimeClockOverlapError):
        await repository.update_entry(
            "entry-1",
            clock_in=datetime(2026, 7, 6, 9, 0, tzinfo=timezone.utc),
            clock_out=datetime(2026, 7, 6, 13, 0, tzinfo=timezone.utc),
        )
