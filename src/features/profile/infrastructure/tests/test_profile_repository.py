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
        "phone": "+34 600 111 222",
        "city": "Madrid",
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
    # Bug real (auditoría QA): el JOIN con el manager debe excluir a los
    # dados de baja EN LA CONDICIÓN DEL JOIN, no solo en el WHERE del
    # usuario principal — si no, un manager soft-eliminado seguía
    # apareciendo como `manager_name`.
    assert "LEFT JOIN users m ON m.id = u.manager_id AND m.deleted_at IS NULL" in query
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
    assert profile.phone == "+34 600 111 222"
    assert profile.city == "Madrid"


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
        phone=None,
        city=None,
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
    assert profile.phone is None
    assert profile.city is None


@pytest.mark.asyncio
async def test_update_profile_contact_upserts_and_returns_the_refreshed_profile():
    """`user_profiles` puede no tener fila para este usuario todavía — el
    repositorio debe UPSERT (INSERT ... ON CONFLICT), no UPDATE, y devolver
    la ficha completa recién leída (con los JOINs de entidad/depto/manager)."""
    pool = AsyncMock()
    pool.fetchrow.return_value = _row(phone="+34 611 222 333", city="Valencia")
    repository = PostgresProfileRepository(pool)

    profile = await repository.update_profile_contact(
        "user-1", phone="+34 611 222 333", city="Valencia"
    )

    assert profile is not None
    assert profile.phone == "+34 611 222 333"
    assert profile.city == "Valencia"

    # `execute` recibe el upsert con los tres parámetros posicionales.
    execute_query, *execute_args = pool.execute.call_args[0]
    assert "INSERT INTO user_profiles" in execute_query
    assert "ON CONFLICT (user_id) DO UPDATE" in execute_query
    assert execute_args == ["user-1", "+34 611 222 333", "Valencia"]

    # Se relee el perfil tras el upsert: dos llamadas a fetchrow (comprobar
    # que el usuario existe + refrescar tras escribir).
    assert pool.fetchrow.call_count == 2


@pytest.mark.asyncio
async def test_update_profile_contact_returns_none_when_user_does_not_exist():
    """No inserta ninguna fila huérfana en `user_profiles` si el usuario del
    token no existe/está borrado — falla ANTES de tocar la tabla."""
    pool = AsyncMock()
    pool.fetchrow.return_value = None
    repository = PostgresProfileRepository(pool)

    profile = await repository.update_profile_contact(
        "missing-user", phone="+34 600 000 000", city="Bilbao"
    )

    assert profile is None
    pool.execute.assert_not_called()
