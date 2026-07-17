from ..application.results import LiveClockStatusResult
from ..application.use_cases.list_time_clock_entries import TimeClockEntryPage
from ..domain.entities import TimeClockEntry, TimeClockEntryNote
from .schemas import (
    OpenTimeClockEntryDTO,
    TimeClockCurrentStatusDTO,
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
