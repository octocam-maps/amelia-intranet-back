from datetime import date

import pytest

from src.features.dashboard.application.use_cases.get_dashboard_summary import (
    GetDashboardSummaryUseCase,
)
from src.features.dashboard.domain.entities import (
    AdminDashboardSummary,
    PendingAbsenceRequestSummary,
    VacationBalanceSummary,
)

from .fakes import FakeDashboardRepository


@pytest.mark.asyncio
async def test_employee_summary_has_no_admin_widgets():
    repository = FakeDashboardRepository(
        vacation_balance=VacationBalanceSummary(entitled_days=23, used_days=5, pending_days=2)
    )
    use_case = GetDashboardSummaryUseCase(repository)

    summary = await use_case.execute(user_id="user-1", role="empleado")

    assert summary.vacation_balance.available_days == 16
    assert not isinstance(summary, AdminDashboardSummary)


@pytest.mark.asyncio
async def test_employee_without_vacation_balance_yet_gets_none_not_an_error():
    """Un usuario recién dado de alta no tiene fila de saldo todavía — el
    dashboard no debe fallar, solo mostrar "sin datos" (`None`)."""
    use_case = GetDashboardSummaryUseCase(FakeDashboardRepository())

    summary = await use_case.execute(user_id="user-1", role="empleado")

    assert summary.vacation_balance is None


@pytest.mark.asyncio
async def test_admin_summary_includes_pending_tray_and_global_view():
    repository = FakeDashboardRepository(
        pending_absence_requests=[
            PendingAbsenceRequestSummary(
                id="r1",
                user_id="user-2",
                user_full_name="Otro Empleado",
                absence_type_name="Vacaciones",
                start_date=date(2026, 7, 20),
                end_date=date(2026, 7, 24),
                days_count=5,
            )
        ],
        employees_clocked_in_now=3,
    )
    use_case = GetDashboardSummaryUseCase(repository)

    summary = await use_case.execute(user_id="admin-1", role="administrador")

    assert isinstance(summary, AdminDashboardSummary)
    assert len(summary.pending_absence_requests) == 1
    assert summary.employees_clocked_in_now == 3
