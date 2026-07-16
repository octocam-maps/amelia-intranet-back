from datetime import date

import pytest

from src.features.staff.application.use_cases.create_staff_member import (
    CreateStaffMemberUseCase,
)
from src.features.staff.domain.errors import (
    InvalidEntityCodeError,
    InvalidRoleCodeError,
    StaffEmailAlreadyExistsError,
)

from .fakes import FakeStaffRepository


@pytest.mark.asyncio
async def test_creates_invited_user_with_initial_vacation_balance():
    repository = FakeStaffRepository()
    use_case = CreateStaffMemberUseCase(repository)

    member = await use_case.execute(
        full_name="Sandra Ramírez",
        email="Sandra@AmeliaHub.com",
        job_title="Project Manager",
        department="Operaciones",
        entity_code="hub",
        role_code="empleado",
        hire_date=date(2026, 1, 12),
        vacation_days_per_year=23,
    )

    assert member.status == "invited"
    assert member.email == "sandra@ameliahub.com"  # normalizado a minúsculas
    assert member.entity_code == "hub"
    assert member.role_code == "empleado"
    assert member.vacation_days_per_year == 23


@pytest.mark.asyncio
async def test_duplicate_email_is_rejected():
    repository = FakeStaffRepository()
    use_case = CreateStaffMemberUseCase(repository)
    await use_case.execute(
        full_name="Sandra Ramírez",
        email="sandra@ameliahub.com",
        job_title=None,
        department=None,
        entity_code="hub",
        role_code="empleado",
        hire_date=None,
        vacation_days_per_year=None,
    )

    with pytest.raises(StaffEmailAlreadyExistsError):
        await use_case.execute(
            full_name="Otra Persona",
            email="sandra@ameliahub.com",
            job_title=None,
            department=None,
            entity_code="lab",
            role_code="empleado",
            hire_date=None,
            vacation_days_per_year=None,
        )


@pytest.mark.asyncio
async def test_unknown_entity_code_is_rejected():
    repository = FakeStaffRepository()
    use_case = CreateStaffMemberUseCase(repository)

    with pytest.raises(InvalidEntityCodeError):
        await use_case.execute(
            full_name="Sandra Ramírez",
            email="sandra@ameliahub.com",
            job_title=None,
            department=None,
            entity_code="not-a-real-entity",
            role_code="empleado",
            hire_date=None,
            vacation_days_per_year=None,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role_code", ["administrador", "empleado", "externo_invitado", "socio"]
)
async def test_creates_a_member_with_each_assignable_role(role_code):
    """Los 4 roles de la tabla `roles` (migración 024 sumó `socio`) deben
    poder darse de alta desde "Plantilla" — regresión del refactor que quitó
    el `Literal[...]` fijo de `staff/infrastructure/schemas.py`: la única
    validación real vive aquí, contra `resolve_role_id`."""
    repository = FakeStaffRepository()
    use_case = CreateStaffMemberUseCase(repository)

    member = await use_case.execute(
        full_name="Persona de Prueba",
        email=f"prueba-{role_code}@ameliahub.com",
        job_title=None,
        department=None,
        entity_code="hub",
        role_code=role_code,
        hire_date=None,
        vacation_days_per_year=None,
    )

    assert member.role_code == role_code


@pytest.mark.asyncio
async def test_unknown_role_code_is_rejected():
    repository = FakeStaffRepository()
    use_case = CreateStaffMemberUseCase(repository)

    with pytest.raises(InvalidRoleCodeError):
        await use_case.execute(
            full_name="Sandra Ramírez",
            email="sandra@ameliahub.com",
            job_title=None,
            department=None,
            entity_code="hub",
            role_code="not-a-real-role",
            hire_date=None,
            vacation_days_per_year=None,
        )
