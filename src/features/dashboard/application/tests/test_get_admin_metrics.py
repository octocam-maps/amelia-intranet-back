from datetime import date

import pytest

from src.features.dashboard.application.use_cases.get_admin_metrics import (
    GetAdminMetricsUseCase,
)
from src.features.dashboard.domain.entities import DailyTrendPoint

from .fakes import FakeDashboardRepository


def _trend(day: date, absences=0, clocked_in=0, punctual=0, total=0) -> DailyTrendPoint:
    return DailyTrendPoint(
        day=day,
        absences=absences,
        clocked_in=clocked_in,
        punctual_entries=punctual,
        total_entries=total,
    )


@pytest.mark.asyncio
async def test_kpis_are_read_straight_from_the_repository_counts():
    repository = FakeDashboardRepository(
        absent_today=3,
        pending_approvals=5,
        clocked_in_now_filtered=7,
    )
    use_case = GetAdminMetricsUseCase(repository)

    metrics = await use_case.execute()

    assert metrics.kpis.absent_today == 3
    assert metrics.kpis.pending_approvals == 5
    assert metrics.kpis.clocked_in_now == 7


@pytest.mark.asyncio
async def test_punctuality_pct_is_derived_from_the_daily_trend_series():
    repository = FakeDashboardRepository(
        daily_trends=[
            _trend(date(2026, 7, 1), punctual=8, total=10),
            _trend(date(2026, 7, 2), punctual=2, total=10),
        ]
    )
    use_case = GetAdminMetricsUseCase(repository)

    metrics = await use_case.execute()

    # (8 + 2) / (10 + 10) * 100 = 50%
    assert metrics.kpis.punctuality_pct == 50


@pytest.mark.asyncio
async def test_punctuality_pct_is_zero_when_the_period_has_no_clock_entries():
    repository = FakeDashboardRepository(
        daily_trends=[_trend(date(2026, 7, 1)), _trend(date(2026, 7, 2))]
    )
    use_case = GetAdminMetricsUseCase(repository)

    metrics = await use_case.execute()

    assert metrics.kpis.punctuality_pct == 0


@pytest.mark.asyncio
async def test_no_data_at_all_returns_zeros():
    use_case = GetAdminMetricsUseCase(FakeDashboardRepository())

    metrics = await use_case.execute()

    assert metrics.kpis.absent_today == 0
    assert metrics.kpis.pending_approvals == 0
    assert metrics.kpis.clocked_in_now == 0
    assert metrics.kpis.punctuality_pct == 0


@pytest.mark.asyncio
async def test_filters_are_forwarded_to_every_repository_call():
    repository = FakeDashboardRepository()
    use_case = GetAdminMetricsUseCase(repository)

    await use_case.execute(entity_id="entity-hub", department_id="dept-1", period_days=7)

    assert repository.received_filters["count_absent_today"] == ("entity-hub", "dept-1")
    assert repository.received_filters["count_pending_absence_approvals"] == (
        "entity-hub",
        "dept-1",
    )
    assert repository.received_filters["count_clocked_in_now_filtered"] == (
        "entity-hub",
        "dept-1",
    )
    assert repository.received_filters["list_daily_trends"] == ("entity-hub", "dept-1")
