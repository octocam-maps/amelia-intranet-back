"""B-2b: incidencias/comentarios admin sobre un tramo de fichaje."""

from datetime import date, datetime, timezone

import pytest

from src.features.time_clock.application.use_cases.add_time_clock_entry_note import (
    AddTimeClockEntryNoteUseCase,
)
from src.features.time_clock.application.use_cases.list_time_clock_entry_notes import (
    ListTimeClockEntryNotesUseCase,
)
from src.features.time_clock.domain.entities import TimeClockEntry
from src.features.time_clock.domain.errors import (
    TimeClockEntryNotFoundError,
    TimeClockForbiddenError,
    TimeClockNoteBodyRequiredError,
)

from .fakes import FakeTimeClockRepository


def _closed_entry(entry_id: str = "entry-1", user_id: str = "user-1") -> TimeClockEntry:
    now = datetime(2026, 7, 9, 6, tzinfo=timezone.utc)
    return TimeClockEntry(
        id=entry_id,
        user_id=user_id,
        work_date=date(2026, 7, 9),
        clock_in=now,
        clock_out=datetime(2026, 7, 9, 14, tzinfo=timezone.utc),
        source="web",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_admin_can_add_note_to_anyones_entry():
    repository = FakeTimeClockRepository(
        [_closed_entry()], full_names={"admin-1": "Beatriz Luna"}
    )
    use_case = AddTimeClockEntryNoteUseCase(repository)

    note = await use_case.execute(
        entry_id="entry-1", author_id="admin-1", body="Olvidó fichar salida, corregido a mano."
    )

    assert note.entry_id == "entry-1"
    assert note.author_id == "admin-1"
    assert note.body == "Olvidó fichar salida, corregido a mano."


@pytest.mark.asyncio
async def test_add_note_rejects_empty_body():
    repository = FakeTimeClockRepository([_closed_entry()])
    use_case = AddTimeClockEntryNoteUseCase(repository)

    with pytest.raises(TimeClockNoteBodyRequiredError):
        await use_case.execute(entry_id="entry-1", author_id="admin-1", body="   ")


@pytest.mark.asyncio
async def test_add_note_rejects_unknown_entry():
    repository = FakeTimeClockRepository([])
    use_case = AddTimeClockEntryNoteUseCase(repository)

    with pytest.raises(TimeClockEntryNotFoundError):
        await use_case.execute(entry_id="missing", author_id="admin-1", body="Incidencia.")


@pytest.mark.asyncio
async def test_notes_are_listed_chronologically_for_an_entry():
    repository = FakeTimeClockRepository([_closed_entry()], full_names={"admin-1": "Beatriz Luna"})
    add_use_case = AddTimeClockEntryNoteUseCase(repository)
    list_use_case = ListTimeClockEntryNotesUseCase(repository)

    await add_use_case.execute(entry_id="entry-1", author_id="admin-1", body="Primera incidencia.")
    await add_use_case.execute(entry_id="entry-1", author_id="admin-1", body="Segunda incidencia.")

    notes = await list_use_case.execute(
        entry_id="entry-1", requester_id="admin-1", requester_role="administrador"
    )

    assert [n.body for n in notes] == ["Primera incidencia.", "Segunda incidencia."]
    assert notes[0].author_full_name == "Beatriz Luna"


@pytest.mark.asyncio
async def test_owner_can_list_their_own_entry_notes():
    repository = FakeTimeClockRepository([_closed_entry()])
    add_use_case = AddTimeClockEntryNoteUseCase(repository)
    list_use_case = ListTimeClockEntryNotesUseCase(repository)

    await add_use_case.execute(entry_id="entry-1", author_id="admin-1", body="Incidencia visible.")

    notes = await list_use_case.execute(
        entry_id="entry-1", requester_id="user-1", requester_role="empleado"
    )

    assert len(notes) == 1


@pytest.mark.asyncio
async def test_other_employee_cannot_list_notes_of_a_foreign_entry():
    repository = FakeTimeClockRepository([_closed_entry()])
    list_use_case = ListTimeClockEntryNotesUseCase(repository)

    with pytest.raises(TimeClockForbiddenError):
        await list_use_case.execute(
            entry_id="entry-1", requester_id="user-2", requester_role="empleado"
        )


@pytest.mark.asyncio
async def test_list_notes_rejects_unknown_entry():
    repository = FakeTimeClockRepository([])
    list_use_case = ListTimeClockEntryNotesUseCase(repository)

    with pytest.raises(TimeClockEntryNotFoundError):
        await list_use_case.execute(
            entry_id="missing", requester_id="admin-1", requester_role="administrador"
        )
