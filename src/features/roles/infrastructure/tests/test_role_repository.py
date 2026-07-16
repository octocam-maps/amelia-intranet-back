"""Mismo patrón de mock de pool que
`features/team/infrastructure/tests/test_team_repository.py`."""

from unittest.mock import AsyncMock

import pytest

from src.features.roles.infrastructure.repositories.role_repository import (
    PostgresRoleRepository,
)


def _role_row(**overrides) -> dict:
    row = {"id": "role-1", "code": "empleado", "name": "Empleado"}
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_list_roles_maps_rows_to_role_entities():
    pool = AsyncMock()
    pool.fetch.return_value = [
        _role_row(id="role-1", code="administrador", name="Administrador"),
        _role_row(id="role-2", code="empleado", name="Empleado"),
        _role_row(id="role-3", code="externo_invitado", name="Externo-invitado"),
        _role_row(id="role-4", code="socio", name="Socio"),
    ]
    repository = PostgresRoleRepository(pool)

    roles = await repository.list_roles()

    assert len(roles) == 4
    assert {role.code for role in roles} == {
        "administrador",
        "empleado",
        "externo_invitado",
        "socio",
    }
    assert roles[0].id == "role-1"
    assert roles[0].name == "Administrador"


@pytest.mark.asyncio
async def test_list_roles_does_not_filter_by_is_system_or_deleted_at():
    """La tabla `roles` no tiene `deleted_at` (no hay soft-delete de roles) —
    esta query nunca debe asumir que existe esa columna."""
    pool = AsyncMock()
    pool.fetch.return_value = []
    repository = PostgresRoleRepository(pool)

    await repository.list_roles()

    query = pool.fetch.call_args[0][0]
    assert "deleted_at" not in query
    assert "FROM roles" in query
