from ..domain.entities import (
    AdminDashboardMetrics,
    AdminDashboardSummary,
    EmployeeDashboardSummary,
)
from .schemas import (
    AdminMetricsDTO,
    AdminMetricsKPIsDTO,
    AdminMetricsTrendsDTO,
    AttendanceRadarItemDTO,
    DashboardSummaryDTO,
    PendingAbsenceRequestDTO,
    TodayClockStatusDTO,
    UpcomingHolidayDTO,
    VacationBalanceDTO,
)


def summary_to_dto(summary: EmployeeDashboardSummary) -> DashboardSummaryDTO:
    vacation_dto = (
        VacationBalanceDTO(
            entitled_days=summary.vacation_balance.entitled_days,
            used_days=summary.vacation_balance.used_days,
            pending_days=summary.vacation_balance.pending_days,
            available_days=summary.vacation_balance.available_days,
        )
        if summary.vacation_balance
        else None
    )
    today_clock_dto = TodayClockStatusDTO(
        has_open_entry=summary.today_clock_status.has_open_entry,
        worked_minutes_today=summary.today_clock_status.worked_minutes_today,
    )
    holidays_dto = [UpcomingHolidayDTO(day=h.day, name=h.name) for h in summary.upcoming_holidays]

    if isinstance(summary, AdminDashboardSummary):
        return DashboardSummaryDTO(
            vacation_balance=vacation_dto,
            today_clock_status=today_clock_dto,
            upcoming_holidays=holidays_dto,
            pending_absence_requests=[
                PendingAbsenceRequestDTO(
                    id=r.id,
                    user_id=r.user_id,
                    user_full_name=r.user_full_name,
                    absence_type_name=r.absence_type_name,
                    start_date=r.start_date,
                    end_date=r.end_date,
                    days_count=r.days_count,
                )
                for r in summary.pending_absence_requests
            ],
            employees_clocked_in_now=summary.employees_clocked_in_now,
        )

    return DashboardSummaryDTO(
        vacation_balance=vacation_dto,
        today_clock_status=today_clock_dto,
        upcoming_holidays=holidays_dto,
    )


def metrics_to_dto(metrics: AdminDashboardMetrics) -> AdminMetricsDTO:
    return AdminMetricsDTO(
        kpis=AdminMetricsKPIsDTO(
            absent_today=metrics.kpis.absent_today,
            pending_approvals=metrics.kpis.pending_approvals,
            clocked_in_now=metrics.kpis.clocked_in_now,
            punctuality_pct=metrics.kpis.punctuality_pct,
        ),
        trends=AdminMetricsTrendsDTO(
            absences=metrics.trends.absences,
            clocked_in=metrics.trends.clocked_in,
            punctuality=metrics.trends.punctuality,
        ),
        attendance_radar=[
            AttendanceRadarItemDTO(
                user_id=item.user_id,
                full_name=item.full_name,
                avatar_url=item.avatar_url,
                kind=item.kind,
                value_minutes=item.value_minutes,
                detail=item.detail,
            )
            for item in metrics.attendance_radar
        ],
    )
