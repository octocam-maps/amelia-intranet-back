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
        # Catálogo 2026 [055]: la mayoría son raíz; solo Software y Hardware
        # tienen padre.
        "parent_department_id": None,
        "parent_name": None,
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
    # [055] Los desactivados por el catálogo 2026 (`Administración`,
    # `Ingeniería`) no se ofrecen para asignaciones nuevas.
    assert "d.is_active" in query
    # Agrupado por sociedad y, dentro, por rama: las hojas van pegadas a su
    # padre (`Producto > Software`), no sueltas en el orden alfabético global.
    assert "ORDER BY e.code, COALESCE(parent.name, d.name)" in query
    assert args == ["user-1"]


@pytest.mark.asyncio
async def test_child_departments_carry_their_parent_name():
    """`Software` y `Hardware` cuelgan de `Producto` [055]. El nombre del padre
    viene resuelto por JOIN para que el selector pueda agrupar sin cruzar la
    lista consigo misma buscando por id."""
    pool = AsyncMock()
    pool.fetch.return_value = [
        _department_row(
            id="dept-sw",
            name="Software",
            parent_department_id="dept-producto",
            parent_name="Producto",
        )
    ]
    repository = PostgresDepartmentRepository(pool)

    departments = await repository.list_departments_for_user("user-1")

    assert departments[0].parent_name == "Producto"
    assert departments[0].parent_department_id == "dept-producto"


@pytest.mark.asyncio
async def test_the_belongs_to_check_does_not_filter_by_is_active():
    """Deliberado: quien ya está en un departamento desactivado por el catálogo
    2026 debe poder seguir guardando su perfil. Filtrar aquí convertiría el
    "desactivar" en el "borrar" que la migración 054 quiso evitar."""
    pool = AsyncMock()
    pool.fetchrow.return_value = {"?column?": 1}
    repository = PostgresDepartmentRepository(pool)

    await repository.department_belongs_to_user_entity("dept-1", "user-1")

    query, *_ = pool.fetchrow.call_args[0]
    assert "is_active" not in query


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
