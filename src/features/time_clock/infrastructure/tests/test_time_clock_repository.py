"""
RACE-3 (auditoría QA Fase 3): `find_overlapping_entry` en el use case es un
check-then-act — el constraint `EXCLUDE` de la migración 012 es la fuente de
verdad real bajo concurrencia. No podemos reproducir la carrera contra un
Postgres real en un test unitario, pero sí la rama de manejo del error: si
asyncpg levanta `ExclusionViolationError`, el repositorio debe traducirla al
error de dominio correcto según la rama — `TimeClockAlreadyClockedInError`
para el fichaje EN VIVO (`clock_out is None`, bug real de auditoría QA: antes
siempre caía en `TimeClockOverlapError`, un mensaje de "se solapa" que no
tiene sentido para un doble clock-in) y `TimeClockOverlapError` para el alta
manual de un tramo completo.
"""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import asyncpg
import pytest

from src.features.time_clock.domain.errors import (
    TimeClockAlreadyClockedInError,
    TimeClockOverlapError,
)
from src.features.time_clock.infrastructure.repositories.time_clock_repository import (
    PostgresTimeClockRepository,
)


def _fake_pool_raising(exc: Exception) -> AsyncMock:
    pool = AsyncMock()
    pool.fetchrow.side_effect = exc
    return pool


@pytest.mark.asyncio
async def test_create_entry_translates_exclusion_violation_to_already_clocked_in_for_live_entry():
    """`clock_out is None` es la rama de fichaje EN VIVO (botón play) — bajo
    carrera, un segundo clock-in choca con el mismo EXCLUDE, pero el mensaje
    correcto es "ya tienes un fichaje en curso", no "se solapa"."""
    pool = _fake_pool_raising(asyncpg.exceptions.ExclusionViolationError("overlap"))
    repository = PostgresTimeClockRepository(pool)

    with pytest.raises(TimeClockAlreadyClockedInError):
        await repository.create_entry(
            user_id="user-1",
            work_date=date(2026, 7, 6),
            clock_in=datetime(2026, 7, 6, 9, 0, tzinfo=timezone.utc),
            clock_out=None,
            source="web",
        )


@pytest.mark.asyncio
async def test_create_entry_translates_exclusion_violation_to_overlap_error_for_manual_entry():
    """Alta manual de un tramo completo (`clock_out` informado): la
    colisión SÍ es un solape de horario, no un doble clock-in."""
    pool = _fake_pool_raising(asyncpg.exceptions.ExclusionViolationError("overlap"))
    repository = PostgresTimeClockRepository(pool)

    with pytest.raises(TimeClockOverlapError):
        await repository.create_entry(
            user_id="user-1",
            work_date=date(2026, 7, 6),
            clock_in=datetime(2026, 7, 6, 9, 0, tzinfo=timezone.utc),
            clock_out=datetime(2026, 7, 6, 13, 0, tzinfo=timezone.utc),
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
