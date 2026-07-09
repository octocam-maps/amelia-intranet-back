from ..domain.entities import TimeClockEntry
from .schemas import TimeClockEntryDTO, TimeClockEntryListDTO


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
