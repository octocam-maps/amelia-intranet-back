import pytest

from src.features.departments.application.use_cases.list_departments import (
    ListDepartmentsUseCase,
)
from src.features.departments.domain.entities import Department

from .fakes import FakeDepartmentRepository


@pytest.mark.asyncio
async def test_list_departments_is_a_pure_pass_through_of_the_repository():
    custom_departments = [
        Department(id="dept-x", name="Marketing", entity_id="entity-lab", entity_code="lab")
    ]
    repository = FakeDepartmentRepository(custom_departments)
    use_case = ListDepartmentsUseCase(repository)

    departments = await use_case.execute()

    assert departments == custom_departments


@pytest.mark.asyncio
async def test_list_departments_returns_every_department():
    repository = FakeDepartmentRepository()
    use_case = ListDepartmentsUseCase(repository)

    departments = await use_case.execute()

    names = {department.name for department in departments}
    assert names == {"Recursos Humanos", "Operaciones"}
