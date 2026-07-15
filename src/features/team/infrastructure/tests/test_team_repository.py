"""
Regresión RGPD: el directorio nunca debe proyectar columnas sensibles de
`user_profiles` (dni_nif/iban/address/social_security_number/birth_date) ni
incluir plantilla suspendida/borrada. El calendario de vacaciones solo debe
consultar tipo `vacaciones` en estado `approved`. Mismo patrón de mock de
pool que `features/absences/infrastructure/tests/test_absences_repository.py`.
"""

from datetime import date
from unittest.mock import AsyncMock

import pytest

from src.features.team.infrastructure.repositories.team_repository import (
    PostgresTeamRepository,
)

_SENSITIVE_COLUMNS = ("dni_nif", "iban", "address", "social_security_number", "birth_date")


def _directory_row(**overrides) -> dict:
    row = {
        "id": "user-1",
        "full_name": "Ana García",
        "job_title": "Técnica de RRHH",
        "email": "ana.garcia@ameliahub.com",
        "avatar_url": None,
        "entity_code": "hub",
        "entity_name": "Amelia Hub",
        "phone": "+34600000000",
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_list_directory_query_never_projects_sensitive_columns():
    pool = AsyncMock()
    pool.fetch.return_value = [_directory_row()]
    repository = PostgresTeamRepository(pool)

    await repository.list_directory()

    query = pool.fetch.call_args[0][0]
    for column in _SENSITIVE_COLUMNS:
        assert column not in query


@pytest.mark.asyncio
async def test_list_directory_excludes_suspended_and_deleted():
    pool = AsyncMock()
    pool.fetch.return_value = [_directory_row()]
    repository = PostgresTeamRepository(pool)

    await repository.list_directory()

    query = pool.fetch.call_args[0][0]
    assert "status != 'suspended'" in query
    assert "deleted_at IS NULL" in query


@pytest.mark.asyncio
async def test_list_directory_maps_rows_to_team_member():
    pool = AsyncMock()
    pool.fetch.return_value = [_directory_row()]
    repository = PostgresTeamRepository(pool)

    members = await repository.list_directory()

    assert len(members) == 1
    assert members[0].full_name == "Ana García"
    assert members[0].entity_code == "hub"
    assert members[0].phone == "+34600000000"


@pytest.mark.asyncio
async def test_list_approved_vacations_filters_by_type_and_status():
    pool = AsyncMock()
    pool.fetch.return_value = [
        {
            "user_id": "user-1",
            "full_name": "Ana García",
            "start_date": date(2026, 7, 20),
            "end_date": date(2026, 7, 24),
        }
    ]
    repository = PostgresTeamRepository(pool)

    entries = await repository.list_approved_vacations(2026, 7)

    query = pool.fetch.call_args[0][0]
    args = pool.fetch.call_args[0][1:]
    assert "t.code = $1" in query
    assert "r.status = 'approved'" in query
    assert args[0] == "vacaciones"
    # El rango de solapamiento cubre todo julio 2026.
    assert args[1] == date(2026, 7, 1)
    assert args[2] == date(2026, 7, 31)
    assert entries[0].full_name == "Ana García"


@pytest.mark.asyncio
async def test_list_approved_vacations_resolves_last_day_of_february_leap_year():
    pool = AsyncMock()
    pool.fetch.return_value = []
    repository = PostgresTeamRepository(pool)

    await repository.list_approved_vacations(2028, 2)

    args = pool.fetch.call_args[0][1:]
    assert args[2] == date(2028, 2, 29)


@pytest.mark.asyncio
async def test_list_upcoming_birthdays_filters_by_internal_not_deleted_not_suspended():
    pool = AsyncMock()
    pool.fetch.return_value = []
    repository = PostgresTeamRepository(pool)

    await repository.list_upcoming_birthdays(today=date(2026, 7, 15), days=7)

    query = pool.fetch.call_args[0][0]
    assert "u.is_external = FALSE" in query
    assert "u.status != 'suspended'" in query
    assert "u.deleted_at IS NULL" in query
    assert "p.birth_date IS NOT NULL" in query


@pytest.mark.asyncio
async def test_list_upcoming_birthdays_never_projects_sensitive_columns():
    pool = AsyncMock()
    pool.fetch.return_value = []
    repository = PostgresTeamRepository(pool)

    await repository.list_upcoming_birthdays(today=date(2026, 7, 15), days=7)

    query = pool.fetch.call_args[0][0]
    for column in ("dni_nif", "iban", "address", "social_security_number"):
        assert column not in query


@pytest.mark.asyncio
async def test_list_upcoming_birthdays_candidates_cover_window_without_year_wrap():
    pool = AsyncMock()
    pool.fetch.return_value = []
    repository = PostgresTeamRepository(pool)

    await repository.list_upcoming_birthdays(today=date(2026, 7, 15), days=7)

    candidates = pool.fetch.call_args[0][1]
    assert candidates == ["07-15", "07-16", "07-17", "07-18", "07-19", "07-20", "07-21"]


@pytest.mark.asyncio
async def test_list_upcoming_birthdays_candidates_wrap_across_year_boundary():
    pool = AsyncMock()
    pool.fetch.return_value = []
    repository = PostgresTeamRepository(pool)

    await repository.list_upcoming_birthdays(today=date(2026, 12, 29), days=7)

    candidates = pool.fetch.call_args[0][1]
    assert candidates == [
        "12-29",
        "12-30",
        "12-31",
        "01-01",
        "01-02",
        "01-03",
        "01-04",
    ]


@pytest.mark.asyncio
async def test_list_upcoming_birthdays_marks_todays_birthday_and_maps_fields():
    pool = AsyncMock()
    pool.fetch.return_value = [
        {
            "id": "user-1",
            "full_name": "Ana García",
            "avatar_url": None,
            "birth_date": date(1990, 7, 15),
        }
    ]
    repository = PostgresTeamRepository(pool)

    entries = await repository.list_upcoming_birthdays(today=date(2026, 7, 15), days=7)

    assert len(entries) == 1
    entry = entries[0]
    assert entry.user_id == "user-1"
    assert entry.full_name == "Ana García"
    assert entry.day == 15
    assert entry.month == 7
    assert not hasattr(entry, "birth_date")
    assert entry.is_today is True


@pytest.mark.asyncio
async def test_list_upcoming_birthdays_orders_by_proximity_today_first():
    pool = AsyncMock()
    pool.fetch.return_value = [
        {
            "id": "user-2",
            "full_name": "Bruno Ruiz",
            "avatar_url": None,
            "birth_date": date(1985, 7, 20),
        },
        {
            "id": "user-1",
            "full_name": "Ana García",
            "avatar_url": None,
            "birth_date": date(1990, 7, 15),
        },
    ]
    repository = PostgresTeamRepository(pool)

    entries = await repository.list_upcoming_birthdays(today=date(2026, 7, 15), days=7)

    assert [entry.full_name for entry in entries] == ["Ana García", "Bruno Ruiz"]
    assert entries[0].is_today is True
    assert entries[1].is_today is False


@pytest.mark.asyncio
async def test_list_upcoming_birthdays_across_year_wrap_marks_january_match():
    pool = AsyncMock()
    pool.fetch.return_value = [
        {
            "id": "user-1",
            "full_name": "Carla Ibáñez",
            "avatar_url": None,
            "birth_date": date(1992, 1, 2),
        }
    ]
    repository = PostgresTeamRepository(pool)

    entries = await repository.list_upcoming_birthdays(today=date(2026, 12, 29), days=7)

    assert len(entries) == 1
    assert entries[0].month == 1
    assert entries[0].day == 2
    assert entries[0].is_today is False
