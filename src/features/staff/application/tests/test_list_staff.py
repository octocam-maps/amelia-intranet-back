import pytest

from src.features.staff.application.use_cases.create_staff_member import (
    CreateStaffMemberUseCase,
)
from src.features.staff.application.use_cases.list_staff import ListStaffUseCase

from .fakes import FakeStaffRepository


@pytest.mark.asyncio
async def test_filters_by_entity_and_search():
    repository = FakeStaffRepository()
    create = CreateStaffMemberUseCase(repository)
    await create.execute(
        full_name="Sandra Ramírez",
        email="sandra@ameliahub.com",
        job_title=None,
        department=None,
        entity_code="hub",
        role_code="empleado",
        hire_date=None,
        vacation_days_per_year=None,
    )
    await create.execute(
        full_name="Daniel Santos",
        email="daniel@amelialab.com",
        job_title=None,
        department=None,
        entity_code="lab",
        role_code="empleado",
        hire_date=None,
        vacation_days_per_year=None,
    )
    use_case = ListStaffUseCase(repository)

    hub_only, hub_total = await use_case.execute(entity_code="hub", search=None)
    assert [m.full_name for m in hub_only] == ["Sandra Ramírez"]
    assert hub_total == 1

    by_name, by_name_total = await use_case.execute(entity_code=None, search="daniel")
    assert [m.full_name for m in by_name] == ["Daniel Santos"]
    assert by_name_total == 1


@pytest.mark.asyncio
async def test_pagination_returns_total_regardless_of_page_size():
    repository = FakeStaffRepository()
    create = CreateStaffMemberUseCase(repository)
    for index in range(3):
        await create.execute(
            full_name=f"Persona {index}",
            email=f"persona{index}@ameliahub.com",
            job_title=None,
            department=None,
            entity_code="hub",
            role_code="empleado",
            hire_date=None,
            vacation_days_per_year=None,
        )
    use_case = ListStaffUseCase(repository)

    first_page, total = await use_case.execute(entity_code=None, search=None, page=1, page_size=2)

    assert len(first_page) == 2
    assert total == 3
