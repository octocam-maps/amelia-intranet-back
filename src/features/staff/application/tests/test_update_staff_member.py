from datetime import date

import pytest

from src.features.staff.application.use_cases.update_staff_member import (
    UpdateStaffMemberUseCase,
)
from src.features.staff.domain.errors import StaffMemberNotFoundError

from .fakes import _DEFAULT_INVITED_BY, FakeStaffRepository, build_create_staff_member_use_case


async def _seed_member(repository: FakeStaffRepository):
    return await build_create_staff_member_use_case(repository).execute(
        full_name="Sandra Ramírez",
        email="sandra@ameliahub.com",
        job_title="Project Manager",
        department=None,
        entity_code="hub",
        role_code="empleado",
        hire_date=None,
        vacation_days_override=23,
        invited_by=_DEFAULT_INVITED_BY,
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
async def test_not_passing_vacation_days_override_leaves_it_untouched():
    """No informar `vacation_days_override` en absoluto (la mayoría de
    ediciones, p. ej. solo cambiar el puesto) no debe tocar el override ni
    recalcular el saldo — mismo patrón que
    `holidays.test_not_passing_entity_code_leaves_the_scope_untouched`."""
    repository = FakeStaffRepository()
    member = await _seed_member(repository)  # override=23 al crear
    use_case = UpdateStaffMemberUseCase(repository)

    updated = await use_case.execute(member.id, job_title="Senior PM")

    assert updated.vacation_days_override == 23
    assert updated.vacation_days_per_year == 23


@pytest.mark.asyncio
async def test_passing_vacation_days_override_none_clears_it_to_automatic():
    """`vacation_days_override=None` EXPLÍCITO (el admin vació el campo en
    el formulario) vuelve al cálculo automático desde `hire_date` — a
    diferencia de "no informarlo" (arriba), que no toca nada."""
    repository = FakeStaffRepository()
    member = await build_create_staff_member_use_case(repository).execute(
        full_name="Marc Roig",
        email="marc@ameliahub.com",
        job_title="Backend",
        department=None,
        entity_code="hub",
        role_code="empleado",
        hire_date=date(2020, 1, 1),  # calcularía 20
        vacation_days_override=15,  # pero el admin lo fijó a 15
        invited_by=_DEFAULT_INVITED_BY,
    )
    use_case = UpdateStaffMemberUseCase(repository)

    updated = await use_case.execute(member.id, vacation_days_override=None)

    assert updated.vacation_days_override is None
    assert updated.vacation_days_per_year == 20  # vuelve al cálculo automático


@pytest.mark.asyncio
async def test_passing_a_new_vacation_days_override_value_overrides_the_calculation():
    repository = FakeStaffRepository()
    member = await build_create_staff_member_use_case(repository).execute(
        full_name="Marc Roig",
        email="marc@ameliahub.com",
        job_title="Backend",
        department=None,
        entity_code="hub",
        role_code="empleado",
        hire_date=date(2020, 1, 1),  # calcularía 20
        vacation_days_override=None,
        invited_by=_DEFAULT_INVITED_BY,
    )
    use_case = UpdateStaffMemberUseCase(repository)

    updated = await use_case.execute(member.id, vacation_days_override=12)

    assert updated.vacation_days_override == 12
    assert updated.vacation_days_per_year == 12


@pytest.mark.asyncio
async def test_updating_missing_member_raises_not_found():
    repository = FakeStaffRepository()
    use_case = UpdateStaffMemberUseCase(repository)

    with pytest.raises(StaffMemberNotFoundError):
        await use_case.execute("does-not-exist", job_title="Nuevo puesto")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role_code", ["administrador", "empleado", "externo_invitado", "socio"]
)
async def test_updates_a_members_role_to_each_assignable_role(role_code):
    """Misma regresión que `test_create_staff_member.py` pero para
    `PATCH /staff/{id}` — editar a alguien (aunque sea solo el puesto) no
    debe rechazar ni degradar ningún rol de la tabla `roles`."""
    repository = FakeStaffRepository()
    member = await _seed_member(repository)
    use_case = UpdateStaffMemberUseCase(repository)

    updated = await use_case.execute(member.id, role_code=role_code)

    assert updated.role_code == role_code
