from ..application.results import (
    CompensationBalance,
    LiveClockStatusResult,
    TechnicianMonthSummary,
    TimeClockEntriesBatchResult,
)
from ..application.use_cases.list_time_clock_entries import TimeClockEntryPage
from ..domain.entities import Project, TechnicianDailyLog, TimeClockEntry, TimeClockEntryNote
from .schemas import (
    CompensationBalanceDTO,
    OmittedBatchDayDTO,
    OpenTimeClockEntryDTO,
    ProjectDTO,
    ProjectListDTO,
    TechnicianDailyLogDTO,
    TechnicianDailyLogListDTO,
    TechnicianMonthSummaryDTO,
    TimeClockCurrentStatusDTO,
    TimeClockEntriesBatchDTO,
    TimeClockEntryDTO,
    TimeClockEntryListDTO,
    TimeClockEntryNoteDTO,
    TimeClockEntryNoteListDTO,
)


def entry_to_dto(entry: TimeClockEntry) -> TimeClockEntryDTO:
    return TimeClockEntryDTO(
        id=entry.id,
        user_id=entry.user_id,
        full_name=entry.full_name,
        work_date=entry.work_date,
        clock_in=entry.clock_in,
        clock_out=entry.clock_out,
        source=entry.source,
        worked_minutes=entry.worked_minutes,
    )


def entries_to_dto(page: TimeClockEntryPage, *, limit: int, offset: int) -> TimeClockEntryListDTO:
    return TimeClockEntryListDTO(
        entries=[entry_to_dto(entry) for entry in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
    )


def batch_result_to_dto(
    result: TimeClockEntriesBatchResult,
) -> TimeClockEntriesBatchDTO:
    return TimeClockEntriesBatchDTO(
        created=[entry_to_dto(entry) for entry in result.created],
        omitted=[
            OmittedBatchDayDTO(work_date=omitted.work_date, reason=omitted.reason)
            for omitted in result.omitted
        ],
    )


def note_to_dto(note: TimeClockEntryNote) -> TimeClockEntryNoteDTO:
    return TimeClockEntryNoteDTO(
        id=note.id,
        entry_id=note.entry_id,
        author_id=note.author_id,
        author_full_name=note.author_full_name,
        body=note.body,
        created_at=note.created_at,
    )


def notes_to_dto(notes: list[TimeClockEntryNote]) -> TimeClockEntryNoteListDTO:
    return TimeClockEntryNoteListDTO(notes=[note_to_dto(note) for note in notes])


def live_status_to_dto(status: LiveClockStatusResult) -> TimeClockCurrentStatusDTO:
    return TimeClockCurrentStatusDTO(
        open_entry=(
            OpenTimeClockEntryDTO(
                id=status.open_entry.id,
                clock_in=status.open_entry.clock_in,
                on_break=status.open_entry.on_break,
            )
            if status.open_entry is not None
            else None
        ),
        week_worked_minutes=status.week_worked_minutes,
        expected_weekly_minutes=status.expected_weekly_minutes,
    )


# --- Parte diario del técnico (requerimiento v1.2 §M1) ---


def daily_log_to_dto(log: TechnicianDailyLog) -> TechnicianDailyLogDTO:
    return TechnicianDailyLogDTO(
        entry_id=log.entry_id,
        user_id=log.user_id,
        full_name=log.full_name,
        work_date=log.work_date,
        started_at=log.started_at,
        ended_at=log.ended_at,
        project_id=log.project_id,
        project_name=log.project_name,
        work_location=log.work_location,
        had_break=log.had_break,
        break_minutes=log.break_minutes,
        overnight_stay=log.overnight_stay.value,
        product_category=log.product_category.value,
        worked_minutes=log.worked_minutes,
    )


def month_summary_to_dto(summary: TechnicianMonthSummary) -> TechnicianMonthSummaryDTO:
    return TechnicianMonthSummaryDTO(
        year=summary.year,
        month=summary.month,
        budget_minutes=summary.budget_minutes,
        worked_minutes=summary.worked_minutes,
        remaining_minutes=summary.remaining_minutes,
        overtime_minutes=summary.overtime_minutes,
        compensation_minutes=summary.compensation_minutes,
        overnight_stays_spain=summary.overnight_stays_spain,
        overnight_stays_abroad=summary.overnight_stays_abroad,
        overnight_stays_total=summary.overnight_stays_total,
        is_closed=summary.is_closed,
    )


def daily_logs_to_dto(
    logs: list[TechnicianDailyLog], summary: TechnicianMonthSummary
) -> TechnicianDailyLogListDTO:
    return TechnicianDailyLogListDTO(
        logs=[daily_log_to_dto(log) for log in logs],
        summary=month_summary_to_dto(summary),
    )


def compensation_balance_to_dto(balance: CompensationBalance) -> CompensationBalanceDTO:
    return CompensationBalanceDTO(
        year=balance.year,
        accrued_minutes=balance.accrued_minutes,
        consumed_minutes=balance.consumed_minutes,
        available_minutes=balance.available_minutes,
        pending_minutes=balance.pending_minutes,
    )


def projects_to_dto(projects: list[Project]) -> ProjectListDTO:
    return ProjectListDTO(
        projects=[
            ProjectDTO(id=project.id, code=project.code, name=project.name)
            for project in projects
        ]
    )
