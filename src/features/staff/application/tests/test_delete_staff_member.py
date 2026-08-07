"""
Baja DEFINITIVA de una persona de la plantilla (soft delete + anonimización).

Lo que se protege aquí no es "que el borrado borre": es que NO borre de más
—el registro de jornada se conserva 4 años (art. 34.9 ET)— y que no deje la
intranet sin nadie que pueda administrarla.
"""

from datetime import date, datetime, timezone

import pytest

from src.features.staff.application.use_cases.delete_staff_member import (
    DeleteStaffMemberUseCase,
)
from src.features.staff.domain.entities import StaffMember
from src.features.staff.domain.errors import (
    CannotDeleteLastAdminError,
    CannotDeleteYourselfError,
    StaffMemberNotFoundError,
)

from .fakes import FakeSessionRevoker, FakeStaffRepository

_ADMIN_ID = "admin-1"
_EMPLOYEE_ID = "empleado-1"


def _member(user_id: str, role_code: str, *, status: str = "active") -> StaffMember:
    return StaffMember(
        id=user_id,
        full_name=f"Persona {user_id}",
        email=f"{user_id}@ameliahub.com",
        avatar_url=None,
        job_title=None,
        contract_type=None,
        department_id=None,
        department_name=None,
        entity_id=None,
        entity_code="hub",
        role_id=f"role-{role_code}",
        role_code=role_code,
        status=status,
        hire_date=date(2026, 1, 1),
        vacation_days_per_year=23,
        vacation_days_override=None,
        vacation_days_calculated=23,
        created_at=datetime.now(timezone.utc),
    )


def _build(members: list[StaffMember]) -> tuple[DeleteStaffMemberUseCase, FakeStaffRepository, FakeSessionRevoker]:
    repository = FakeStaffRepository(members)
    revoker = FakeSessionRevoker()
    return DeleteStaffMemberUseCase(repository, revoker), repository, revoker


@pytest.mark.asyncio
async def test_deletes_an_employee_and_revokes_their_sessions():
    use_case, repository, revoker = _build(
        [_member(_ADMIN_ID, "administrador"), _member(_EMPLOYEE_ID, "empleado")]
    )

    await use_case.execute(user_id=_EMPLOYEE_ID, requester_id=_ADMIN_ID)

    assert _EMPLOYEE_ID in repository.deleted_member_ids
    # Sin revocar, quien acaba de ser dado de baja seguiría navegando con su
    # access token hasta que caducara.
    assert revoker.revoked_user_ids == [_EMPLOYEE_ID]


@pytest.mark.asyncio
async def test_the_row_is_not_removed_only_marked():
    """El borrado es LÓGICO. `users` es el nodo raíz de fichajes, ausencias y
    documentos firmados: un DELETE real se los llevaría por CASCADE, y el
    registro de jornada hay que conservarlo 4 años."""
    use_case, repository, _ = _build(
        [_member(_ADMIN_ID, "administrador"), _member(_EMPLOYEE_ID, "empleado")]
    )

    await use_case.execute(user_id=_EMPLOYEE_ID, requester_id=_ADMIN_ID)

    assert _EMPLOYEE_ID in repository.members


@pytest.mark.asyncio
async def test_an_admin_cannot_delete_themselves():
    """La baja revoca las sesiones: quien la ejecutase sobre sí mismo perdería
    el acceso a mitad de la operación."""
    use_case, _, _ = _build([_member(_ADMIN_ID, "administrador")])

    with pytest.raises(CannotDeleteYourselfError):
        await use_case.execute(user_id=_ADMIN_ID, requester_id=_ADMIN_ID)


@pytest.mark.asyncio
async def test_the_last_active_admin_cannot_be_deleted():
    """`docs/permisos-roles.md` define un único administrador, así que esto no
    es hipotético: es el error de un clic. Sin admin no hay forma de nombrar
    otro desde la propia aplicación."""
    otro_admin = _member("admin-2", "administrador")
    use_case, _, _ = _build([_member(_ADMIN_ID, "administrador"), otro_admin])

    # `admin-2` borra a `admin-1`: quedaría él, así que se permite.
    await use_case.execute(user_id=_ADMIN_ID, requester_id="admin-2")

    # Ahora `admin-2` es el último. Otro admin cualquiera intentaría borrarlo
    # y no debe poder — se comprueba con el requester distinto para no chocar
    # antes con la regla de "no a ti mismo".
    with pytest.raises(CannotDeleteLastAdminError):
        await use_case.execute(user_id="admin-2", requester_id=_ADMIN_ID)


@pytest.mark.asyncio
async def test_a_suspended_admin_does_not_count_as_cover():
    """Un administrador suspendido no puede entrar, así que dejarlo como único
    'superviviente' equivaldría a quedarse sin ninguno."""
    use_case, _, _ = _build(
        [
            _member(_ADMIN_ID, "administrador"),
            _member("admin-suspendido", "administrador", status="suspended"),
        ]
    )

    with pytest.raises(CannotDeleteLastAdminError):
        await use_case.execute(user_id=_ADMIN_ID, requester_id="admin-suspendido")


@pytest.mark.asyncio
async def test_deleting_an_employee_never_checks_the_admin_rule():
    """Regresión de la implementación: la comprobación del último admin solo
    aplica a administradores. Ejecutarla siempre bloquearía dar de baja a un
    empleado cuando solo hay un admin, que es el caso NORMAL de esta empresa."""
    use_case, repository, _ = _build(
        [_member(_ADMIN_ID, "administrador"), _member(_EMPLOYEE_ID, "empleado")]
    )

    await use_case.execute(user_id=_EMPLOYEE_ID, requester_id=_ADMIN_ID)

    assert _EMPLOYEE_ID in repository.deleted_member_ids


@pytest.mark.asyncio
async def test_deleting_someone_who_does_not_exist():
    use_case, _, _ = _build([_member(_ADMIN_ID, "administrador")])

    with pytest.raises(StaffMemberNotFoundError):
        await use_case.execute(user_id="no-existe", requester_id=_ADMIN_ID)
