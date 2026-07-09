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
