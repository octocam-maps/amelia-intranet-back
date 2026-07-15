from datetime import date

import pytest

from src.features.dashboard.application.use_cases.get_admin_metrics import (
    GetAdminMetricsUseCase,
)
from src.features.dashboard.domain.entities import DailyTrendPoint, EmployeeAttendanceStats

from .fakes import FakeDashboardRepository


def _trend(day: date, absences=0, clocked_in=0, punctual=0, total=0) -> DailyTrendPoint:
    return DailyTrendPoint(
        day=day,
        absences=absences,
        clocked_in=clocked_in,
        punctual_entries=punctual,
        total_entries=total,
    )


def _stat(
    user_id: str,
    full_name: str,
    *,
    days_clocked: int = 10,
    worked_minutes_total: int,
    avg_clock_in_minutes: float,
    avg_clock_out_minutes: float,
    avatar_url=None,
) -> EmployeeAttendanceStats:
    return EmployeeAttendanceStats(
        user_id=user_id,
        full_name=full_name,
        avatar_url=avatar_url,
        days_clocked=days_clocked,
        worked_minutes_total=worked_minutes_total,
        avg_clock_in_minutes=avg_clock_in_minutes,
        avg_clock_out_minutes=avg_clock_out_minutes,
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
async def test_punctuality_pct_is_derived_from_the_same_daily_series_as_the_trend():
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
    assert metrics.trends.punctuality == [80, 20]


@pytest.mark.asyncio
async def test_punctuality_pct_is_zero_when_the_period_has_no_clock_entries():
    repository = FakeDashboardRepository(
        daily_trends=[_trend(date(2026, 7, 1)), _trend(date(2026, 7, 2))]
    )
    use_case = GetAdminMetricsUseCase(repository)

    metrics = await use_case.execute()

    assert metrics.kpis.punctuality_pct == 0
    assert metrics.trends.punctuality == [0, 0]


@pytest.mark.asyncio
async def test_no_data_at_all_returns_zeros_and_empty_lists_never_null():
    use_case = GetAdminMetricsUseCase(FakeDashboardRepository())

    metrics = await use_case.execute()

    assert metrics.kpis.absent_today == 0
    assert metrics.kpis.pending_approvals == 0
    assert metrics.kpis.clocked_in_now == 0
    assert metrics.kpis.punctuality_pct == 0
    assert metrics.trends.absences == []
    assert metrics.trends.clocked_in == []
    assert metrics.trends.punctuality == []
    assert metrics.attendance_radar == []


@pytest.mark.asyncio
async def test_trends_length_matches_the_period_and_keeps_chronological_order():
    repository = FakeDashboardRepository(
        daily_trends=[
            _trend(date(2026, 7, 1), absences=1, clocked_in=4, punctual=4, total=4),
            _trend(date(2026, 7, 2), absences=0, clocked_in=5, punctual=3, total=5),
            _trend(date(2026, 7, 3), absences=2, clocked_in=3, punctual=3, total=3),
        ]
    )
    use_case = GetAdminMetricsUseCase(repository)

    metrics = await use_case.execute(period_days=3)

    assert metrics.trends.absences == [1, 0, 2]
    assert metrics.trends.clocked_in == [4, 5, 3]
    assert metrics.trends.punctuality == [100, 60, 100]


@pytest.mark.asyncio
async def test_attendance_radar_classifies_each_employee_by_dominant_deviation():
    # 10 días fichados, jornada estándar 8h = 480 min/día -> esperado 4800 min.
    late_employee = _stat(
        "user-late",
        "Empleado Tarde",
        worked_minutes_total=4800,
        avg_clock_in_minutes=9 * 60 + 45,  # entra de media a las 09:45 -> 45 min tarde
        avg_clock_out_minutes=19 * 60,
    )
    overtime_employee = _stat(
        "user-overtime",
        "Empleado Horas Extra",
        worked_minutes_total=4800,
        avg_clock_in_minutes=9 * 60,
        avg_clock_out_minutes=19 * 60 + 80,  # sale de media a las 20:20 -> 80 min de más
    )
    negative_balance_employee = _stat(
        "user-deficit",
        "Empleado Déficit",
        worked_minutes_total=4650,  # 4800 - 4650 = 150 min de déficit
        avg_clock_in_minutes=9 * 60,
        avg_clock_out_minutes=19 * 60,
    )
    on_time_employee = _stat(
        "user-on-time",
        "Empleado Puntual",
        worked_minutes_total=4800,
        avg_clock_in_minutes=9 * 60,
        avg_clock_out_minutes=19 * 60,
    )
    repository = FakeDashboardRepository(
        attendance_stats=[
            late_employee,
            overtime_employee,
            negative_balance_employee,
            on_time_employee,
        ]
    )
    use_case = GetAdminMetricsUseCase(repository)

    metrics = await use_case.execute()

    radar_by_user = {item.user_id: item for item in metrics.attendance_radar}
    assert radar_by_user["user-late"].kind == "late_in"
    assert radar_by_user["user-late"].value_minutes == 45
    assert radar_by_user["user-overtime"].kind == "overtime_out"
    assert radar_by_user["user-overtime"].value_minutes == 80
    assert radar_by_user["user-deficit"].kind == "negative_balance"
    assert radar_by_user["user-deficit"].value_minutes == 150
    assert radar_by_user["user-on-time"].kind == "on_time"
    assert radar_by_user["user-on-time"].value_minutes == 0


@pytest.mark.asyncio
async def test_attendance_radar_returns_top_5_ordered_desc_by_magnitude():
    stats = [
        _stat(
            "user-1",
            "Uno",
            worked_minutes_total=4800,
            avg_clock_in_minutes=9 * 60 + 90,  # 90 min tarde
            avg_clock_out_minutes=19 * 60,
        ),
        _stat(
            "user-2",
            "Dos",
            worked_minutes_total=4800,
            avg_clock_in_minutes=9 * 60 + 20,  # 20 min tarde
            avg_clock_out_minutes=19 * 60,
        ),
        _stat(
            "user-3",
            "Tres",
            worked_minutes_total=4800,
            avg_clock_in_minutes=9 * 60,
            avg_clock_out_minutes=19 * 60 + 60,  # 60 min de más
        ),
        _stat(
            "user-4",
            "Cuatro",
            worked_minutes_total=4200,  # déficit 600
            avg_clock_in_minutes=9 * 60,
            avg_clock_out_minutes=19 * 60,
        ),
        _stat(
            "user-5",
            "Cinco",
            worked_minutes_total=4800,
            avg_clock_in_minutes=9 * 60,
            avg_clock_out_minutes=19 * 60,
        ),
        _stat(
            "user-6",
            "Seis",
            worked_minutes_total=4800,
            avg_clock_in_minutes=9 * 60 + 5,  # 5 min, por debajo del umbral -> on_time
            avg_clock_out_minutes=19 * 60,
        ),
    ]
    repository = FakeDashboardRepository(attendance_stats=stats)
    use_case = GetAdminMetricsUseCase(repository)

    metrics = await use_case.execute()

    assert len(metrics.attendance_radar) == 5
    magnitudes = [item.value_minutes for item in metrics.attendance_radar]
    assert magnitudes == sorted(magnitudes, reverse=True)
    kinds = {item.kind for item in metrics.attendance_radar}
    # Con datos para los 3 tipos de desvío, la demo debe mostrar variedad.
    assert {"late_in", "overtime_out", "negative_balance"}.issubset(kinds)
    # user-4 (déficit 600) es la mayor magnitud absoluta -> primero.
    assert metrics.attendance_radar[0].user_id == "user-4"


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
    assert repository.received_filters["list_attendance_stats"] == ("entity-hub", "dept-1")
