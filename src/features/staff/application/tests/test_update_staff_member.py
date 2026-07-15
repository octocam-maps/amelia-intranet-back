import pytest

from src.features.staff.application.use_cases.create_staff_member import (
    CreateStaffMemberUseCase,
)
from src.features.staff.application.use_cases.update_staff_member import (
    UpdateStaffMemberUseCase,
)
from src.features.staff.domain.errors import StaffMemberNotFoundError

from .fakes import FakeStaffRepository


async def _seed_member(repository: FakeStaffRepository):
    return await CreateStaffMemberUseCase(repository).execute(
        full_name="Sandra Ramírez",
        email="sandra@ameliahub.com",
        job_title="Project Manager",
        department=None,
        entity_code="hub",
        role_code="empleado",
        hire_date=None,
        vacation_days_per_year=23,
    )


@pytest.mark.asyncio
async def test_deactivating_sets_status_to_suspended():
    repository = FakeStaffRepository()
    member = await _seed_member(repository)
    use_case = UpdateStaffMemberUseCase(repository)

    updated = await use_case.execute(member.id, is_active=False)

    assert updated.status == "suspended"


@pytest.mark.asyncio
async def test_partial_update_leaves_other_fields_untouched():
    repository = FakeStaffRepository()
    member = await _seed_member(repository)
    use_case = UpdateStaffMemberUseCase(repository)

    updated = await use_case.execute(member.id, job_title="Senior PM")

    assert updated.job_title == "Senior PM"
    assert updated.vacation_days_per_year == 23
    assert updated.entity_code == "hub"
    assert updated.status == "invited"


@pytest.mark.asyncio
async def test_updating_missing_member_raises_not_found():
    repository = FakeStaffRepository()
    use_case = UpdateStaffMemberUseCase(repository)

    with pytest.raises(StaffMemberNotFoundError):
        await use_case.execute("does-not-exist", job_title="Nuevo puesto")
