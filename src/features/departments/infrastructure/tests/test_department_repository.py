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

    departments = await repository.list_departments_for_user("user-1")

    assert len(departments) == 2
    assert {department.name for department in departments} == {
        "Recursos Humanos",
        "Operaciones",
    }
    assert departments[0].id == "dept-1"
    assert departments[0].entity_code == "hub"


@pytest.mark.asyncio
async def test_list_departments_filters_by_the_users_entity():
    """El filtro es lo que arregla el selector: sin él devolvía los mismos cinco
    departamentos repetidos en las cuatro sociedades, 20 filas, y el paso 4
    mostraba cuatro «Administración» indistinguibles.

    Se comprueba en la QUERY y no en el resultado porque el filtro lo hace
    Postgres: un mock del pool devuelve lo que se le diga, así que lo único
    verificable aquí es que el SQL lo pide y con el usuario correcto."""
    pool = AsyncMock()
    pool.fetch.return_value = []
    repository = PostgresDepartmentRepository(pool)

    await repository.list_departments_for_user("user-1")

    query, *args = pool.fetch.call_args[0]
    assert "FROM departments" in query
    assert "LEFT JOIN entities" in query
    assert "SELECT entity_id FROM users WHERE id = $1" in query
    # El `OR ... IS NULL` es el fallback del usuario sin entidad: sin él no vería
    # NINGÚN departamento y no podría completar el paso 4.
    assert "IS NULL" in query
    # Agrupado por sociedad, que es lo que hace legible el caso ambiguo.
    assert "ORDER BY e.code, d.name" in query
    assert args == ["user-1"]


@pytest.mark.asyncio
async def test_department_belongs_to_user_entity_checks_both_id_and_entity():
    """La validación del backend, que hace falta ADEMÁS del filtro del listado:
    el desplegable es solo UI y enviar otro `department_id` a mano se la salta."""
    pool = AsyncMock()
    pool.fetchrow.return_value = {"?column?": 1}
    repository = PostgresDepartmentRepository(pool)

    assert await repository.department_belongs_to_user_entity("dept-1", "user-1") is True

    query, *args = pool.fetchrow.call_args[0]
    assert "FROM departments" in query
    assert "d.id = $1" in query
    assert "SELECT entity_id FROM users WHERE id = $2" in query
    assert args == ["dept-1", "user-1"]


@pytest.mark.asyncio
async def test_department_belongs_to_user_entity_is_false_when_no_row_matches():
    """Cubre los dos casos que la query resuelve igual: el departamento no existe,
    o existe pero es de otra sociedad."""
    pool = AsyncMock()
    pool.fetchrow.return_value = None
    repository = PostgresDepartmentRepository(pool)

    assert await repository.department_belongs_to_user_entity("dept-x", "user-1") is False
