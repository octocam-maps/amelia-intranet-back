"""Wiring de FastAPI: construye los casos de uso con sus adaptadores concretos."""

from src.shared.config import get_settings
from src.shared.database import get_database_pool

from ..application.use_cases.add_time_clock_entry_note import AddTimeClockEntryNoteUseCase
from ..application.use_cases.clock_in import ClockInUseCase
from ..application.use_cases.clock_out import ClockOutUseCase
from ..application.use_cases.create_time_clock_entries_batch import (
    CreateTimeClockEntriesBatchUseCase,
)
from ..application.use_cases.create_technician_daily_log import (
    CreateTechnicianDailyLogUseCase,
)
from ..application.use_cases.create_time_clock_entry import CreateTimeClockEntryUseCase
from ..application.use_cases.delete_technician_daily_log import (
    DeleteTechnicianDailyLogUseCase,
)
from ..application.use_cases.delete_time_clock_entry import DeleteTimeClockEntryUseCase
from ..application.use_cases.end_break import EndBreakUseCase
from ..application.use_cases.export_time_clock_entries import ExportTimeClockEntriesUseCase
from ..application.use_cases.get_compensation_balance import GetCompensationBalanceUseCase
from ..application.use_cases.get_live_status import GetLiveStatusUseCase
from ..application.use_cases.list_projects import ListProjectsUseCase
from ..application.use_cases.list_technician_daily_logs import (
    ListTechnicianDailyLogsUseCase,
)
from ..application.use_cases.list_time_clock_entries import ListTimeClockEntriesUseCase
from ..application.use_cases.list_time_clock_entry_notes import ListTimeClockEntryNotesUseCase
from ..application.use_cases.start_break import StartBreakUseCase
from ..application.use_cases.update_technician_daily_log import (
    UpdateTechnicianDailyLogUseCase,
)
from ..application.use_cases.update_time_clock_entry import UpdateTimeClockEntryUseCase
from .repositories.time_clock_repository import PostgresTimeClockRepository


def _get_repository() -> PostgresTimeClockRepository:
    return PostgresTimeClockRepository(get_database_pool())


def get_create_time_clock_entry_use_case() -> CreateTimeClockEntryUseCase:
    settings = get_settings()
    return CreateTimeClockEntryUseCase(
        _get_repository(), settings.time_clock_manual_entry_max_past_days
    )


def get_create_time_clock_entries_batch_use_case() -> (
    CreateTimeClockEntriesBatchUseCase
):
    settings = get_settings()
    repository = _get_repository()
    unit_use_case = CreateTimeClockEntryUseCase(
        repository, settings.time_clock_manual_entry_max_past_days
    )
    return CreateTimeClockEntriesBatchUseCase(
        repository, unit_use_case, settings.time_clock_manual_entry_max_past_days
    )


def get_list_time_clock_entries_use_case() -> ListTimeClockEntriesUseCase:
    return ListTimeClockEntriesUseCase(_get_repository())


def get_update_time_clock_entry_use_case() -> UpdateTimeClockEntryUseCase:
    return UpdateTimeClockEntryUseCase(_get_repository())


def get_delete_time_clock_entry_use_case() -> DeleteTimeClockEntryUseCase:
    return DeleteTimeClockEntryUseCase(_get_repository())


def get_clock_in_use_case() -> ClockInUseCase:
    return ClockInUseCase(_get_repository())


def get_clock_out_use_case() -> ClockOutUseCase:
    return ClockOutUseCase(_get_repository())


def get_start_break_use_case() -> StartBreakUseCase:
    return StartBreakUseCase(_get_repository())


def get_end_break_use_case() -> EndBreakUseCase:
    return EndBreakUseCase(_get_repository())


def get_live_status_use_case() -> GetLiveStatusUseCase:
    return GetLiveStatusUseCase(_get_repository())


def get_export_time_clock_entries_use_case() -> ExportTimeClockEntriesUseCase:
    return ExportTimeClockEntriesUseCase(_get_repository())


def get_add_time_clock_entry_note_use_case() -> AddTimeClockEntryNoteUseCase:
    return AddTimeClockEntryNoteUseCase(_get_repository())


def get_list_time_clock_entry_notes_use_case() -> ListTimeClockEntryNotesUseCase:
    return ListTimeClockEntryNotesUseCase(_get_repository())


# --- Parte diario del técnico (requerimiento v1.2 §M1) ---


def get_create_technician_daily_log_use_case() -> CreateTechnicianDailyLogUseCase:
    settings = get_settings()
    # Misma ventana temporal que el alta manual: el parte también es
    # autodeclarado, así que hereda el límite de LOGIC-2.
    return CreateTechnicianDailyLogUseCase(
        _get_repository(), settings.time_clock_manual_entry_max_past_days
    )


def get_update_technician_daily_log_use_case() -> UpdateTechnicianDailyLogUseCase:
    return UpdateTechnicianDailyLogUseCase(_get_repository())


def get_delete_technician_daily_log_use_case() -> DeleteTechnicianDailyLogUseCase:
    return DeleteTechnicianDailyLogUseCase(_get_repository())


def get_list_technician_daily_logs_use_case() -> ListTechnicianDailyLogsUseCase:
    return ListTechnicianDailyLogsUseCase(_get_repository())


def get_compensation_balance_use_case() -> GetCompensationBalanceUseCase:
    return GetCompensationBalanceUseCase(_get_repository())


def get_list_projects_use_case() -> ListProjectsUseCase:
    return ListProjectsUseCase(_get_repository())
