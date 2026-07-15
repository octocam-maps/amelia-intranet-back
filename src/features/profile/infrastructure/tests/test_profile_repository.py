"""
Tests del adaptador asyncpg de `profile` con el pool mockeado (mismo
patrón que `features/staff/infrastructure/tests/test_staff_repository.py`).
"""

from datetime import date
from unittest.mock import AsyncMock

import pytest

from src.features.profile.infrastructure.repositories.profile_repository import (
    PostgresProfileRepository,
)


def _row(**overrides) -> dict:
    row = {
        "id": "user-1",
        "email": "sandra@ameliahub.com",
        "full_name": "Sandra Ramírez",
        "avatar_url": "https://example.com/avatar.png",
        "job_title": "Project Manager",
        "hire_date": date(2022, 3, 1),
        "is_external": False,
        "role_code": "empleado",
        "entity_name": "Amelia Hub",
        "department_name": "Operaciones",
        "manager_name": "Beatriz Luna",
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_find_profile_by_user_id_maps_all_joined_fields():
    pool = AsyncMock()
    pool.fetchrow.return_value = _row()
    repository = PostgresProfileRepository(pool)

    profile = await repository.find_profile_by_user_id("user-1")

    query, *args = pool.fetchrow.call_args[0]
    assert "WHERE u.id = $1 AND u.deleted_at IS NULL" in query
    assert "LEFT JOIN users m ON m.id = u.manager_id" in query
    assert args == ["user-1"]

    assert profile is not None
    assert profile.id == "user-1"
    assert profile.email == "sandra@ameliahub.com"
    assert profile.role_code == "empleado"
    assert profile.entity_name == "Amelia Hub"
    assert profile.department_name == "Operaciones"
    assert profile.manager_name == "Beatriz Luna"
    assert profile.hire_date == date(2022, 3, 1)
    assert profile.is_external is False


@pytest.mark.asyncio
async def test_find_profile_by_user_id_returns_none_when_missing():
    pool = AsyncMock()
    pool.fetchrow.return_value = None
    repository = PostgresProfileRepository(pool)

    assert await repository.find_profile_by_user_id("missing-user") is None


@pytest.mark.asyncio
async def test_find_profile_maps_nulls_for_user_without_entity_department_or_manager():
    pool = AsyncMock()
    pool.fetchrow.return_value = _row(
        job_title=None,
        entity_name=None,
        department_name=None,
        manager_name=None,
        hire_date=None,
        role_code="externo_invitado",
        is_external=True,
    )
    repository = PostgresProfileRepository(pool)

    profile = await repository.find_profile_by_user_id("user-2")

    assert profile is not None
    assert profile.job_title is None
    assert profile.entity_name is None
    assert profile.department_name is None
    assert profile.manager_name is None
    assert profile.hire_date is None
    assert profile.role_code == "externo_invitado"
    assert profile.is_external is True
