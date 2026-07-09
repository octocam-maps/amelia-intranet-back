from ..application.results import LiveClockStatusResult
from ..domain.entities import TimeClockEntry
from .schemas import (
    OpenTimeClockEntryDTO,
    TimeClockCurrentStatusDTO,
    TimeClockEntryDTO,
    TimeClockEntryListDTO,
)


def entry_to_dto(entry: TimeClockEntry) -> TimeClockEntryDTO:
    return TimeClockEntryDTO(
        id=entry.id,
        user_id=entry.user_id,
        work_date=entry.work_date,
        clock_in=entry.clock_in,
        clock_out=entry.clock_out,
        source=entry.source,
        worked_minutes=entry.worked_minutes,
    )


def entries_to_dto(entries: list[TimeClockEntry]) -> TimeClockEntryListDTO:
    return TimeClockEntryListDTO(entries=[entry_to_dto(entry) for entry in entries])


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
