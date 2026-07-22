from datetime import date, datetime, timedelta, timezone

import pytest

from src.features.staff.application.use_cases.create_staff_member import (
    CreateStaffMemberUseCase,
)
from src.features.staff.domain.errors import (
    InvalidEntityCodeError,
    InvalidRoleCodeError,
    StaffEmailAlreadyExistsError,
)

from .fakes import FakeDriveFolderProvisioner, FakeEmailSender, FakeStaffRepository

_INVITED_BY = "admin-1"


def _build_use_case(
    repository=None,
    email_sender=None,
    invitation_expires_days=7,
    drive_folder_provisioner=None,
):
    return CreateStaffMemberUseCase(
        repository or FakeStaffRepository(),
        email_sender or FakeEmailSender(),
        invitation_expires_days,
        "http://localhost:5173",
        drive_folder_provisioner,
    )


@pytest.mark.asyncio
async def test_creates_invited_user_with_initial_vacation_balance():
    repository = FakeStaffRepository()
    use_case = _build_use_case(repository)

    member = await use_case.execute(
        full_name="Sandra Ramírez",
        email="Sandra@AmeliaHub.com",
        job_title="Project Manager",
        department="Operaciones",
        entity_code="hub",
        role_code="empleado",
        hire_date=date(2026, 1, 12),
        vacation_days_override=23,
        invited_by=_INVITED_BY,
    )

    assert member.status == "invited"
    assert member.email == "sandra@ameliahub.com"  # normalizado a minúsculas
    assert member.entity_code == "hub"
    assert member.role_code == "empleado"
    assert member.vacation_days_per_year == 23


@pytest.mark.asyncio
async def test_creates_invitation_row_and_sends_the_invited_email():
    """Área 1 del design (`invitations`): el alta debe dejar traza en
    `invitations` (misma transacción que `users` en Postgres — aquí,
    mismo repo fake) y disparar el aviso por email vía `IEmailSender`."""
    repository = FakeStaffRepository()
    email_sender = FakeEmailSender()
    use_case = _build_use_case(repository, email_sender, invitation_expires_days=7)

    member = await use_case.execute(
        full_name="Sandra Ramírez",
        email="sandra@ameliahub.com",
        job_title=None,
        department=None,
        entity_code="hub",
        role_code="empleado",
        hire_date=None,
        vacation_days_override=None,
        invited_by=_INVITED_BY,
    )

    assert len(repository.invitations) == 1
    invitation = repository.invitations[0]
    assert invitation.email == "sandra@ameliahub.com"
    assert invitation.invited_by == _INVITED_BY
    # `expires_at` = ahora + INVITATION_EXPIRES_DAYS (7 en este test) —
    # margen amplio para no depender de la velocidad de ejecución del test.
    expected_expiry = datetime.now(timezone.utc) + timedelta(days=7)
    assert abs((invitation.expires_at - expected_expiry).total_seconds()) < 5

    assert len(email_sender.sent) == 1
    sent = email_sender.sent[0]
    assert sent["to"] == member.email
    assert sent["template"] == "staff_invited"
    assert sent["context"]["full_name"] == member.full_name
    assert sent["user_id"] == member.id


@pytest.mark.asyncio
async def test_email_failure_does_not_revert_the_staff_alta():
    """Best-effort (mismo criterio que `NotifyUseCase.execute`): si el envío
    del aviso falla, la persona sigue dada de alta — RRHH puede reenviarlo a
    mano desde el feature `invitations`."""
    repository = FakeStaffRepository()
    email_sender = FakeEmailSender(fail_for={"sandra@ameliahub.com"})
    use_case = _build_use_case(repository, email_sender)

    member = await use_case.execute(
        full_name="Sandra Ramírez",
        email="sandra@ameliahub.com",
        job_title=None,
        department=None,
        entity_code="hub",
        role_code="empleado",
        hire_date=None,
        vacation_days_override=None,
        invited_by=_INVITED_BY,
    )

    assert member.status == "invited"
    assert len(repository.invitations) == 1  # la fila de invitations ya se creó
    assert email_sender.sent == []  # el envío falló y no dejó traza de éxito


@pytest.mark.asyncio
async def test_successful_staff_creation_triggers_drive_folder_provisioning():
    """Decisión de producto "hook en alta + batch de backfill": toda alta
    exitosa debe disparar el provisioning de la carpeta de Drive del
    empleado (best-effort, `IDriveFolderProvisioner`)."""
    repository = FakeStaffRepository()
    provisioner = FakeDriveFolderProvisioner()
    use_case = _build_use_case(repository, drive_folder_provisioner=provisioner)

    member = await use_case.execute(
        full_name="Sandra Ramírez",
        email="sandra@ameliahub.com",
        job_title=None,
        department=None,
        entity_code="hub",
        role_code="empleado",
        hire_date=None,
        vacation_days_override=None,
        invited_by=_INVITED_BY,
    )

    assert provisioner.calls == [(member.id, member.email)]


@pytest.mark.asyncio
async def test_drive_folder_provisioning_failure_does_not_revert_the_staff_alta():
    """Best-effort OBLIGATORIO: un fallo de Drive (timeout, credenciales,
    error de API) NUNCA debe revertir ni bloquear el alta del empleado — la
    carpeta se resuelve luego (batch de backfill o primer upload manual)."""
    repository = FakeStaffRepository()
    provisioner = FakeDriveFolderProvisioner(fail_for={"sandra@ameliahub.com"})
    use_case = _build_use_case(repository, drive_folder_provisioner=provisioner)

    member = await use_case.execute(
        full_name="Sandra Ramírez",
        email="sandra@ameliahub.com",
        job_title=None,
        department=None,
        entity_code="hub",
        role_code="empleado",
        hire_date=None,
        vacation_days_override=None,
        invited_by=_INVITED_BY,
    )

    assert member.status == "invited"  # el alta se completó igual
    assert len(repository.invitations) == 1
    assert provisioner.calls == [(member.id, member.email)]  # se intentó


@pytest.mark.asyncio
async def test_duplicate_email_is_rejected():
    repository = FakeStaffRepository()
    use_case = _build_use_case(repository)
    await use_case.execute(
        full_name="Sandra Ramírez",
        email="sandra@ameliahub.com",
        job_title=None,
        department=None,
        entity_code="hub",
        role_code="empleado",
        hire_date=None,
        vacation_days_override=None,
        invited_by=_INVITED_BY,
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
            vacation_days_override=None,
            invited_by=_INVITED_BY,
        )


@pytest.mark.asyncio
async def test_unknown_entity_code_is_rejected():
    repository = FakeStaffRepository()
    use_case = _build_use_case(repository)

    with pytest.raises(InvalidEntityCodeError):
        await use_case.execute(
            full_name="Sandra Ramírez",
            email="sandra@ameliahub.com",
            job_title=None,
            department=None,
            entity_code="not-a-real-entity",
            role_code="empleado",
            hire_date=None,
            vacation_days_override=None,
            invited_by=_INVITED_BY,
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
    use_case = _build_use_case(repository)

    member = await use_case.execute(
        full_name="Persona de Prueba",
        email=f"prueba-{role_code}@ameliahub.com",
        job_title=None,
        department=None,
        entity_code="hub",
        role_code=role_code,
        hire_date=None,
        vacation_days_override=None,
        invited_by=_INVITED_BY,
    )

    assert member.role_code == role_code


@pytest.mark.asyncio
async def test_unknown_role_code_is_rejected():
    repository = FakeStaffRepository()
    use_case = _build_use_case(repository)

    with pytest.raises(InvalidRoleCodeError):
        await use_case.execute(
            full_name="Sandra Ramírez",
            email="sandra@ameliahub.com",
            job_title=None,
            department=None,
            entity_code="hub",
            role_code="not-a-real-role",
            hire_date=None,
            vacation_days_override=None,
            invited_by=_INVITED_BY,
        )
