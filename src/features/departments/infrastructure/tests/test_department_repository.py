"""Mismo patrón de mock de pool que
`features/roles/infrastructure/tests/test_role_repository.py`."""

from unittest.mock import AsyncMock

import pytest

from src.features.departments.infrastructure.repositories.department_repository import (
    PostgresDepartmentRepository,
)


def _department_row(**overrides) -> dict:
    row = {
        "id": "dept-1",
        "name": "Recursos Humanos",
        "entity_id": "entity-hub",
        "entity_code": "hub",
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_list_departments_maps_rows_to_department_entities():
    pool = AsyncMock()
    pool.fetch.return_value = [
        _department_row(id="dept-1", name="Recursos Humanos", entity_code="hub"),
        _department_row(id="dept-2", name="Operaciones", entity_id="entity-ops", entity_code="ops"),
    ]
    repository = PostgresDepartmentRepository(pool)

    departments = await repository.list_departments()

    assert len(departments) == 2
    assert {department.name for department in departments} == {
        "Recursos Humanos",
        "Operaciones",
    }
    assert departments[0].id == "dept-1"
    assert departments[0].entity_code == "hub"


@pytest.mark.asyncio
async def test_list_departments_left_joins_entities_and_orders_by_name():
    """`entity_code` puede venir NULL si un departamento quedara sin
    entidad válida (no debería pasar por el FK NOT NULL, pero el JOIN es
    LEFT por robustez) — y el listado se ordena por nombre para un
    selector estable en el frontend."""
    pool = AsyncMock()
    pool.fetch.return_value = []
    repository = PostgresDepartmentRepository(pool)

    await repository.list_departments()

    query = pool.fetch.call_args[0][0]
    assert "LEFT JOIN entities" in query
    assert "ORDER BY d.name" in query
    assert "FROM departments" in query
