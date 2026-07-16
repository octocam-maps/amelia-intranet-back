"""
RACE-3 (auditoría QA Fase 3): `find_overlapping_entry` en el use case es un
check-then-act — el constraint `EXCLUDE` de la migración 012 es la fuente de
verdad real bajo concurrencia. No podemos reproducir la carrera contra un
Postgres real en un test unitario, pero sí la rama de manejo del error: si
asyncpg levanta `ExclusionViolationError`, el repositorio debe traducirla al
error de dominio correcto según la rama — `TimeClockAlreadyClockedInError`
para el fichaje EN VIVO (`clock_out is None`, bug real de auditoría QA: antes
siempre caía en `TimeClockOverlapError`, un mensaje de "se solapa" que no
tiene sentido para un doble clock-in) y `TimeClockOverlapError` para el alta
manual de un tramo completo.
"""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import asyncpg
import pytest

from src.features.time_clock.domain.errors import (
    TimeClockAlreadyClockedInError,
    TimeClockOverlapError,
)
from src.features.time_clock.infrastructure.repositories.time_clock_repository import (
    PostgresTimeClockRepository,
)


def _fake_pool_raising(exc: Exception) -> AsyncMock:
    pool = AsyncMock()
    pool.fetchrow.side_effect = exc
    return pool


@pytest.mark.asyncio
async def test_create_entry_translates_exclusion_violation_to_already_clocked_in_for_live_entry():
    """`clock_out is None` es la rama de fichaje EN VIVO (botón play) — bajo
    carrera, un segundo clock-in choca con el mismo EXCLUDE, pero el mensaje
    correcto es "ya tienes un fichaje en curso", no "se solapa"."""
    pool = _fake_pool_raising(asyncpg.exceptions.ExclusionViolationError("overlap"))
    repository = PostgresTimeClockRepository(pool)

    with pytest.raises(TimeClockAlreadyClockedInError):
        await repository.create_entry(
            user_id="user-1",
            work_date=date(2026, 7, 6),
            clock_in=datetime(2026, 7, 6, 9, 0, tzinfo=timezone.utc),
            clock_out=None,
            source="web",
        )


@pytest.mark.asyncio
async def test_create_entry_translates_exclusion_violation_to_overlap_error_for_manual_entry():
    """Alta manual de un tramo completo (`clock_out` informado): la
    colisión SÍ es un solape de horario, no un doble clock-in."""
    pool = _fake_pool_raising(asyncpg.exceptions.ExclusionViolationError("overlap"))
    repository = PostgresTimeClockRepository(pool)

    with pytest.raises(TimeClockOverlapError):
        await repository.create_entry(
            user_id="user-1",
            work_date=date(2026, 7, 6),
            clock_in=datetime(2026, 7, 6, 9, 0, tzinfo=timezone.utc),
            clock_out=datetime(2026, 7, 6, 13, 0, tzinfo=timezone.utc),
            source="web",
        )


@pytest.mark.asyncio
async def test_update_entry_translates_exclusion_violation_to_overlap_error():
    pool = _fake_pool_raising(asyncpg.exceptions.ExclusionViolationError("overlap"))
    repository = PostgresTimeClockRepository(pool)

    with pytest.raises(TimeClockOverlapError):
        await repository.update_entry(
            "entry-1",
            clock_in=datetime(2026, 7, 6, 9, 0, tzinfo=timezone.utc),
            clock_out=datetime(2026, 7, 6, 13, 0, tzinfo=timezone.utc),
        )


# --- Lote 1 (feedback post-demo): X-BUG (nombre por JOIN) + X1 (paginación) ---


def _list_row(**overrides) -> dict:
    row = {
        "id": "entry-1",
        "user_id": "user-1",
        "work_date": date(2026, 7, 6),
        "clock_in": datetime(2026, 7, 6, 9, 0, tzinfo=timezone.utc),
        "clock_out": datetime(2026, 7, 6, 13, 0, tzinfo=timezone.utc),
        "source": "web",
        "created_at": datetime(2026, 7, 6, 9, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 7, 6, 9, 0, tzinfo=timezone.utc),
        "full_name": "Ana García",
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_list_entries_for_user_joins_users_for_full_name():
    """X-BUG: la columna "Empleado" mostraba el UUID — el listado debe
    resolver `full_name` vía JOIN a `users`, igual que `_EXPORT_SELECT`."""
    pool = AsyncMock()
    pool.fetch.return_value = [_list_row()]
    repository = PostgresTimeClockRepository(pool)

    entries = await repository.list_entries_for_user(
        "user-1",
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
        limit=50,
        offset=0,
    )

    query = pool.fetch.call_args[0][0]
    assert "JOIN users u ON u.id = e.user_id" in query
    assert entries[0].full_name == "Ana García"


@pytest.mark.asyncio
async def test_list_entries_for_user_applies_limit_and_offset():
    """X1: ~850 fichajes/mes son demasiados para cargar de golpe."""
    pool = AsyncMock()
    pool.fetch.return_value = [_list_row()]
    repository = PostgresTimeClockRepository(pool)

    await repository.list_entries_for_user(
        "user-1",
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
        limit=20,
        offset=40,
    )

    query, *args = pool.fetch.call_args[0]
    assert "LIMIT $4 OFFSET $5" in query
    assert args == ["user-1", date(2026, 7, 1), date(2026, 7, 31), 20, 40]


@pytest.mark.asyncio
async def test_list_entries_for_user_without_limit_returns_full_range():
    """El export CSV llama con `limit=None`: sin `LIMIT`/`OFFSET` en la
    query, para exportar TODO el rango, no solo una página."""
    pool = AsyncMock()
    pool.fetch.return_value = [_list_row()]
    repository = PostgresTimeClockRepository(pool)

    await repository.list_entries_for_user(
        "user-1",
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
        limit=None,
        offset=0,
    )

    query, *args = pool.fetch.call_args[0]
    assert "LIMIT" not in query
    assert args == ["user-1", date(2026, 7, 1), date(2026, 7, 31)]


@pytest.mark.asyncio
async def test_count_entries_for_user_counts_without_pagination():
    pool = AsyncMock()
    pool.fetchval.return_value = 137
    repository = PostgresTimeClockRepository(pool)

    total = await repository.count_entries_for_user(
        "user-1", date_from=date(2026, 7, 1), date_to=date(2026, 7, 31)
    )

    assert total == 137
    query, *args = pool.fetchval.call_args[0]
    assert "COUNT(*)" in query
    assert args == ["user-1", date(2026, 7, 1), date(2026, 7, 31)]


@pytest.mark.asyncio
async def test_list_entries_for_users_filters_by_any_of_the_given_ids():
    """Multi-selector de personas (Lote 2): mismo JOIN/paginación que
    `list_entries_for_user`, pero con `WHERE user_id = ANY(...)`."""
    pool = AsyncMock()
    pool.fetch.return_value = [_list_row(user_id="user-2", full_name="Beatriz Luna")]
    repository = PostgresTimeClockRepository(pool)

    entries = await repository.list_entries_for_users(
        ["user-1", "user-2"],
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
        limit=50,
        offset=0,
    )

    query, *args = pool.fetch.call_args[0]
    assert "e.user_id = ANY($1::uuid[])" in query
    assert "JOIN users u ON u.id = e.user_id" in query
    assert "LIMIT $4 OFFSET $5" in query
    assert args == [["user-1", "user-2"], date(2026, 7, 1), date(2026, 7, 31), 50, 0]
    assert entries[0].full_name == "Beatriz Luna"


@pytest.mark.asyncio
async def test_count_entries_for_users_counts_without_pagination():
    pool = AsyncMock()
    pool.fetchval.return_value = 42
    repository = PostgresTimeClockRepository(pool)

    total = await repository.count_entries_for_users(
        ["user-1", "user-2"], date_from=date(2026, 7, 1), date_to=date(2026, 7, 31)
    )

    assert total == 42
    query, *args = pool.fetchval.call_args[0]
    assert "user_id = ANY($1::uuid[])" in query
    assert args == [["user-1", "user-2"], date(2026, 7, 1), date(2026, 7, 31)]


@pytest.mark.asyncio
async def test_list_entries_for_all_joins_users_and_paginates():
    """Vista aumentada del admin: mismo JOIN + paginación que
    `list_entries_for_user`, sin filtrar por `user_id`."""
    pool = AsyncMock()
    pool.fetch.return_value = [_list_row(user_id="user-2", full_name="Beatriz Luna")]
    repository = PostgresTimeClockRepository(pool)

    entries = await repository.list_entries_for_all(
        date_from=date(2026, 7, 1), date_to=date(2026, 7, 31), limit=50, offset=0
    )

    query, *args = pool.fetch.call_args[0]
    assert "JOIN users u ON u.id = e.user_id" in query
    assert "LIMIT $3 OFFSET $4" in query
    assert args == [date(2026, 7, 1), date(2026, 7, 31), 50, 0]
    assert entries[0].full_name == "Beatriz Luna"


@pytest.mark.asyncio
async def test_count_entries_for_all_counts_without_pagination():
    pool = AsyncMock()
    pool.fetchval.return_value = 850
    repository = PostgresTimeClockRepository(pool)

    total = await repository.count_entries_for_all(
        date_from=date(2026, 7, 1), date_to=date(2026, 7, 31)
    )

    assert total == 850
    query, *args = pool.fetchval.call_args[0]
    assert "COUNT(*)" in query
    assert args == [date(2026, 7, 1), date(2026, 7, 31)]


# --- Incidencias/comentarios sobre un tramo (B-2b) ---


@pytest.mark.asyncio
async def test_add_note_inserts_and_returns_the_note():
    pool = AsyncMock()
    pool.fetchrow.return_value = {
        "id": "note-1",
        "entry_id": "entry-1",
        "author_id": "admin-1",
        "body": "Olvidó fichar salida, corregido a mano.",
        "created_at": datetime(2026, 7, 9, 10, 0, tzinfo=timezone.utc),
    }
    repository = PostgresTimeClockRepository(pool)

    note = await repository.add_note(
        entry_id="entry-1", author_id="admin-1", body="Olvidó fichar salida, corregido a mano."
    )

    query, *args = pool.fetchrow.call_args[0]
    assert "INSERT INTO time_clock_entry_notes" in query
    assert args == ["entry-1", "admin-1", "Olvidó fichar salida, corregido a mano."]
    assert note.id == "note-1"
    assert note.author_full_name is None  # el INSERT no resuelve el JOIN


@pytest.mark.asyncio
async def test_list_notes_for_entry_joins_users_for_author_name():
    pool = AsyncMock()
    pool.fetch.return_value = [
        {
            "id": "note-1",
            "entry_id": "entry-1",
            "author_id": "admin-1",
            "body": "Incidencia.",
            "created_at": datetime(2026, 7, 9, 10, 0, tzinfo=timezone.utc),
            "author_full_name": "Beatriz Luna",
        }
    ]
    repository = PostgresTimeClockRepository(pool)

    notes = await repository.list_notes_for_entry("entry-1")

    query, *args = pool.fetch.call_args[0]
    assert "LEFT JOIN users u ON u.id = n.author_id" in query
    assert args == ["entry-1"]
    assert notes[0].author_full_name == "Beatriz Luna"
