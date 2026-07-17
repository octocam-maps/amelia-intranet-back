"""
Tests del adaptador asyncpg para `GET /dashboard/admin/metrics`, con el pool
mockeado (mismo patrón que
`features/absences/infrastructure/tests/test_absences_repository.py`): se
comprueba que el repositorio construye el SQL correcto (filtros opcionales
de entidad/departamento, hora de Madrid, `generate_series` para no perder
días sin datos) y que mapea las filas a las entidades de dominio.
"""

from datetime import date
from unittest.mock import AsyncMock

import pytest

from src.features.dashboard.infrastructure.repositories.dashboard_repository import (
    PostgresDashboardRepository,
)


@pytest.mark.asyncio
async def test_count_absent_today_filters_by_approved_status_and_date_range():
    pool = AsyncMock()
    pool.fetchval.return_value = 3
    repository = PostgresDashboardRepository(pool)

    result = await repository.count_absent_today(date(2026, 7, 15), None, None)

    assert result == 3
    query, *args = pool.fetchval.call_args[0]
    assert "status = 'approved'" in query
    assert "BETWEEN r.start_date AND r.end_date" in query
    assert args == [date(2026, 7, 15), None, None]


@pytest.mark.asyncio
async def test_count_absent_today_returns_zero_when_no_row_matches():
    pool = AsyncMock()
    pool.fetchval.return_value = None
    repository = PostgresDashboardRepository(pool)

    result = await repository.count_absent_today(date(2026, 7, 15), None, None)

    assert result == 0


@pytest.mark.asyncio
async def test_count_pending_absence_approvals_filters_by_entity_and_departments():
    pool = AsyncMock()
    pool.fetchval.return_value = 2
    repository = PostgresDashboardRepository(pool)

    await repository.count_pending_absence_approvals("entity-hub", ["dept-1", "dept-2"])

    query, *args = pool.fetchval.call_args[0]
    assert "status = 'pending'" in query
    assert "u.entity_id = $1::uuid" in query
    assert "u.department_id = ANY($2::uuid[])" in query
    assert args == ["entity-hub", ["dept-1", "dept-2"]]


@pytest.mark.asyncio
async def test_count_clocked_in_now_filtered_uses_work_date_and_open_entries():
    pool = AsyncMock()
    pool.fetchval.return_value = 5
    repository = PostgresDashboardRepository(pool)

    await repository.count_clocked_in_now_filtered(date(2026, 7, 15), None, ["dept-1"])

    query, *args = pool.fetchval.call_args[0]
    assert "t.work_date = $1" in query
    assert "t.clock_out IS NULL" in query
    assert args == [date(2026, 7, 15), None, ["dept-1"]]


@pytest.mark.asyncio
async def test_list_daily_trends_uses_generate_series_and_madrid_timezone():
    pool = AsyncMock()
    pool.fetch.side_effect = [
        [
            {"day": date(2026, 7, 1), "total_entries": 4, "punctual_entries": 3},
            {"day": date(2026, 7, 2), "total_entries": 0, "punctual_entries": 0},
        ],
        [
            {"day": date(2026, 7, 1), "absences": 1},
            {"day": date(2026, 7, 2), "absences": 0},
        ],
    ]
    repository = PostgresDashboardRepository(pool)

    points = await repository.list_daily_trends(
        date(2026, 7, 1), date(2026, 7, 2), None, None
    )

    clock_query = pool.fetch.call_args_list[0].args[0]
    assert "generate_series($1::date, $2::date" in clock_query
    assert "AT TIME ZONE 'Europe/Madrid'" in clock_query
    absence_query = pool.fetch.call_args_list[1].args[0]
    assert "generate_series($1::date, $2::date" in absence_query
    assert "status = 'approved'" in absence_query

    assert points[0].day == date(2026, 7, 1)
    assert points[0].absences == 1
    assert points[0].clocked_in == 4
    assert points[0].total_entries == 4
    assert points[0].punctual_entries == 3
    assert points[1].absences == 0
    assert points[1].clocked_in == 0
    assert points[1].total_entries == 0


@pytest.mark.asyncio
async def test_list_daily_trends_defaults_missing_absence_day_to_zero():
    """El día existe en la serie de fichajes pero no tiene fila en la
    consulta de ausencias (nadie ausente ese día) -> debe rellenarse con 0,
    nunca faltar la clave."""
    pool = AsyncMock()
    pool.fetch.side_effect = [
        [{"day": date(2026, 7, 1), "total_entries": 0, "punctual_entries": 0}],
        [],
    ]
    repository = PostgresDashboardRepository(pool)

    points = await repository.list_daily_trends(
        date(2026, 7, 1), date(2026, 7, 1), None, None
    )

    assert points[0].absences == 0


