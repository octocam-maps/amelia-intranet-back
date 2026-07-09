"""
Tests del adaptador asyncpg de `holidays` con el pool mockeado (mismo
patrón que `features/staff/infrastructure/tests/test_staff_repository.py`).
"""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.features.holidays.domain.entities import OfficialHoliday
from src.features.holidays.infrastructure.repositories.holiday_repository import (
    PostgresHolidayRepository,
)


def _row(**overrides) -> dict:
    row = {
        "id": "hol-1",
        "day": date(2026, 12, 25),
        "name": "Navidad",
        "entity_id": None,
        "entity_code": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "source": "manual",
        "scope": None,
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_list_holidays_filters_by_year_and_entity():
    pool = AsyncMock()
    pool.fetch.return_value = [_row()]
    repository = PostgresHolidayRepository(pool)

    await repository.list_holidays(year=2026, entity_code="hub")

    query, *args = pool.fetch.call_args[0]
    assert "EXTRACT(YEAR FROM h.day) = $1" in query
    # El filtro de entidad también deja pasar los festivos "para todas"
    # (entity_id IS NULL) — no es un filtro excluyente.
    assert "h.entity_id IS NULL" in query
    assert args == [2026, "hub"]


@pytest.mark.asyncio
async def test_update_holiday_returns_none_when_not_found():
    pool = AsyncMock()
    pool.fetchval.return_value = None
    repository = PostgresHolidayRepository(pool)

    result = await repository.update_holiday(
        "missing-id", day=None, name="x", entity_id=None, clear_entity=False
    )

    assert result is None


@pytest.mark.asyncio
async def test_delete_holiday_returns_true_when_a_row_was_removed():
    pool = AsyncMock()
    pool.fetchval.return_value = "hol-1"
    repository = PostgresHolidayRepository(pool)

    deleted = await repository.delete_holiday("hol-1")

    assert deleted is True


@pytest.mark.asyncio
async def test_import_official_inserts_updates_and_skips_manual():
    pool = AsyncMock()
    # Un día por item: no existe (insert), existe manual (skip), existe oficial (update).
    pool.fetchrow.side_effect = [
        None,
        {"id": "hol-manual", "source": "manual"},
        {"id": "hol-oficial", "source": "oficial"},
    ]
    repository = PostgresHolidayRepository(pool)

    summary = await repository.import_official_holidays(
        [
            OfficialHoliday(day=date(2026, 6, 24), name="Sant Joan", scope="autonomico"),
            OfficialHoliday(day=date(2026, 9, 24), name="La Mercè oficial?", scope="nacional"),
            OfficialHoliday(day=date(2026, 1, 1), name="Año Nuevo", scope="nacional"),
        ]
    )

    assert (summary.imported, summary.updated, summary.skipped) == (1, 1, 1)
    # Solo dos escrituras: el insert del nuevo y el update del oficial; el
    # manual NO genera ningún execute.
    assert pool.execute.await_count == 2
    statements = [call.args[0] for call in pool.execute.await_args_list]
    assert any("INSERT INTO holidays" in s for s in statements)
    assert any("UPDATE holidays" in s for s in statements)
