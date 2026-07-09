import uuid
from datetime import date, datetime, timezone

import pytest

from src.features.holidays.application.use_cases.list_holidays import ListHolidaysUseCase
from src.features.holidays.domain.entities import Holiday

from .fakes import FakeHolidayRepository


def _holiday(day: date, entity_id=None) -> Holiday:
    now = datetime.now(timezone.utc)
    return Holiday(
        id=str(uuid.uuid4()),
        day=day,
        name="Festivo",
        entity_id=entity_id,
        entity_code=None,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_filters_by_year():
    repository = FakeHolidayRepository(
        [_holiday(date(2026, 1, 1)), _holiday(date(2027, 1, 1))]
    )
    use_case = ListHolidaysUseCase(repository)

    result = await use_case.execute(year=2026)

    assert len(result) == 1
    assert result[0].day.year == 2026


@pytest.mark.asyncio
async def test_entity_filter_also_returns_holidays_that_apply_to_everyone():
    repository = FakeHolidayRepository(
        [
            _holiday(date(2026, 1, 1), entity_id="entity-hub"),
            _holiday(date(2026, 5, 1), entity_id="entity-lab"),
            _holiday(date(2026, 12, 25), entity_id=None),
        ]
    )
    use_case = ListHolidaysUseCase(repository)

    result = await use_case.execute(entity_code="hub")

    assert {h.entity_id for h in result} == {"entity-hub", None}
