"""Tests de `ListDepartmentsUseCase`.

Ya NO es un pass-through: el listado depende de QUIÉN pregunta. Los mismos cinco
departamentos existen en las cuatro sociedades del grupo (`departments` tiene
`UNIQUE(entity_id, name)`), así que devolverlos todos hacía que el selector del
paso 4 mostrara cuatro «Administración» indistinguibles."""

import pytest

from src.features.departments.application.use_cases.list_departments import (
    ListDepartmentsUseCase,
)
from src.features.departments.domain.entities import Department

from .fakes import FakeDepartmentRepository

# El caso que provocó el bug: el MISMO nombre repetido en varias sociedades.
_REPETIDOS = [
    Department(id="d-hub", name="Administración", entity_id="e-hub", entity_code="hub"),
    Department(id="d-lab", name="Administración", entity_id="e-lab", entity_code="lab"),
    Department(id="d-ops", name="Administración", entity_id="e-ops", entity_code="ops"),
    Department(id="d-hub-2", name="Comercial", entity_id="e-hub", entity_code="hub"),
]


@pytest.mark.asyncio
async def test_only_returns_the_departments_of_the_users_entity():
    """El caso del bug: con cuatro «Administración» en pantalla, elegir era elegir
    a ciegas y tres de cada cuatro veces se acertaba con la sociedad equivocada."""
    repository = FakeDepartmentRepository(_REPETIDOS, entity_by_user={"u-1": "e-hub"})
    use_case = ListDepartmentsUseCase(repository)

    departments = await use_case.execute(user_id="u-1")

    assert {d.id for d in departments} == {"d-hub", "d-hub-2"}
    # Y ya no quedan dos opciones con el mismo texto:
    nombres = [d.name for d in departments]
    assert len(nombres) == len(set(nombres))


@pytest.mark.asyncio
async def test_a_user_without_entity_gets_all_of_them():
    """Fallback deliberado: hoy hay un empleado con `entity_id` a NULL. Filtrar a
    cero le impediría completar el paso 4 y lo dejaría atascado en su onboarding,
    que es peor que enseñarle una lista ambigua — para ese caso el cliente muestra
    la sociedad junto al nombre."""
    repository = FakeDepartmentRepository(_REPETIDOS, entity_by_user={"u-1": None})
    use_case = ListDepartmentsUseCase(repository)

    departments = await use_case.execute(user_id="u-1")

    assert len(departments) == len(_REPETIDOS)


@pytest.mark.asyncio
async def test_an_unknown_user_gets_all_of_them_instead_of_none():
    """Un `user_id` que no está en el mapa se trata como "sin entidad", no como
    "sin departamentos": el criterio es no bloquear nunca el paso."""
    repository = FakeDepartmentRepository(_REPETIDOS)
    use_case = ListDepartmentsUseCase(repository)

    departments = await use_case.execute(user_id="u-desconocido")

    assert len(departments) == len(_REPETIDOS)


@pytest.mark.asyncio
async def test_returns_an_empty_list_when_the_entity_has_no_departments():
    """Sin departamentos en su sociedad devuelve vacío, y es correcto: quien lo
    consume debe decirlo, no ofrecer los de otra entidad."""
    repository = FakeDepartmentRepository(_REPETIDOS, entity_by_user={"u-1": "e-sin"})
    use_case = ListDepartmentsUseCase(repository)

    assert await use_case.execute(user_id="u-1") == []


@pytest.mark.asyncio
async def test_the_department_still_carries_its_entity_code():
    """El cliente lo necesita para etiquetar la opción cuando la lista sigue
    siendo ambigua (el caso del usuario sin sociedad)."""
    repository = FakeDepartmentRepository(_REPETIDOS, entity_by_user={"u-1": "e-lab"})
    use_case = ListDepartmentsUseCase(repository)

    departments = await use_case.execute(user_id="u-1")

    assert [d.entity_code for d in departments] == ["lab"]
