from ..application.results import LiveClockStatusResult
from ..domain.entities import TimeClockBreak, TimeClockEntry
from .schemas import (
    LiveClockStatusDTO,
    TimeClockBreakDTO,
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


def break_to_dto(break_: TimeClockBreak) -> TimeClockBreakDTO:
    return TimeClockBreakDTO(
        id=break_.id,
        entry_id=break_.entry_id,
        break_start=break_.break_start,
        break_end=break_.break_end,
    )


def live_status_to_dto(status: LiveClockStatusResult) -> LiveClockStatusDTO:
    return LiveClockStatusDTO(
        has_open_entry=status.has_open_entry,
        clock_in=status.clock_in,
        has_open_break=status.has_open_break,
        break_start=status.break_start,
        worked_seconds_today=status.worked_seconds_today,
        week_worked_seconds=status.week_worked_seconds,
        week_target_seconds=status.week_target_seconds,
    )
