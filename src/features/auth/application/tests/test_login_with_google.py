import pytest

from src.features.auth.application.use_cases.login_with_google import (
    LoginWithGoogleUseCase,
)
from src.features.auth.domain.entities import AuthenticatedUser, PendingInvitation
from src.features.auth.domain.errors import EmailNotVerifiedError, NotInvitedError, UserSuspendedError

from .fakes import (
    FakeGoogleIdentity,
    FakeGoogleVerifier,
    FakeJWTService,
    FakeSessionRepository,
    FakeUserRepository,
)


def _build_use_case(user_repo: FakeUserRepository, identity: FakeGoogleIdentity):
    session_repo = FakeSessionRepository()
    use_case = LoginWithGoogleUseCase(
        user_repository=user_repo,
        session_repository=session_repo,
        google_verifier=FakeGoogleVerifier(identity),
        jwt_service=FakeJWTService(),
    )
    return use_case, session_repo


@pytest.mark.asyncio
async def test_auto_provisions_internal_user_without_invitation():
    """hd == ameliahub.com y sin invitación -> alta automática como empleado activo."""
    identity = FakeGoogleIdentity(
        sub="google-sub-1",
        email="nueva.empleada@ameliahub.com",
        email_verified=True,
        full_name="Nueva Empleada",
        avatar_url=None,
        hosted_domain="ameliahub.com",
        is_internal=True,
    )
    user_repo = FakeUserRepository()
    use_case, session_repo = _build_use_case(user_repo, identity)

    result = await use_case.execute("fake-id-token")

    assert result.user.role_code == "empleado"
    assert result.user.status == "active"
    assert result.user.is_external is False
    assert len(user_repo.users) == 1
    assert len(session_repo.sessions) == 1  # login persiste una sesión (jti)


@pytest.mark.asyncio
async def test_auto_provisions_second_internal_domain_user_as_empleado_not_socio():
    """octocam-maps.com se agregó como segundo dominio interno
    (GOOGLE_WORKSPACE_HOSTED_DOMAINS). El auto-alta sigue siendo SIEMPRE
    `empleado` por defecto — el rol `socio` no se otorga automáticamente por
    dominio, lo asigna RRHH a mano después."""
    identity = FakeGoogleIdentity(
        sub="google-sub-octocam-1",
        email="nuevo.socio@octocam-maps.com",
        email_verified=True,
        full_name="Nuevo Colaborador",
        avatar_url=None,
        hosted_domain="octocam-maps.com",
        is_internal=True,
    )
    user_repo = FakeUserRepository()
    use_case, session_repo = _build_use_case(user_repo, identity)

    result = await use_case.execute("fake-id-token")

    assert result.user.role_code == "empleado"
    assert result.user.status == "active"
    assert result.user.is_external is False
    assert len(user_repo.users) == 1


@pytest.mark.asyncio
async def test_external_without_invitation_is_rejected():
    """hd ausente (Gmail personal) y sin invitación -> 403 NotInvitedError."""
    identity = FakeGoogleIdentity(
        sub="google-sub-2",
        email="colaborador@gmail.com",
        email_verified=True,
        full_name="Colaborador Externo",
        avatar_url=None,
        hosted_domain=None,
        is_internal=False,
    )
    use_case, _ = _build_use_case(FakeUserRepository(), identity)

    with pytest.raises(NotInvitedError):
        await use_case.execute("fake-id-token")


@pytest.mark.asyncio
async def test_unlisted_hosted_domain_without_invitation_is_rejected():
    """`hd` presente pero fuera de GOOGLE_WORKSPACE_HOSTED_DOMAINS (Workspace
    de otra empresa) y sin invitación -> 403 NotInvitedError. Distinto del
    caso Gmail personal: aquí SÍ hay `hd`, solo que no está en la lista."""
    identity = FakeGoogleIdentity(
        sub="google-sub-otra-empresa",
        email="alguien@otra-empresa.com",
        email_verified=True,
        full_name="Alguien de Otra Empresa",
        avatar_url=None,
        hosted_domain="otra-empresa.com",
        is_internal=False,
    )
    use_case, _ = _build_use_case(FakeUserRepository(), identity)

    with pytest.raises(NotInvitedError):
        await use_case.execute("fake-id-token")


@pytest.mark.asyncio
async def test_seeded_admin_logs_in_with_administrador_role():
    """El seed 007 (Beatriz) debe entrar como administradora, no auto-provisionarse."""
    seeded_admin = AuthenticatedUser(
        id="admin-1",
        email="beatriz.luna@ameliahub.com",
        full_name="Beatriz Luna",
        avatar_url=None,
        role_code="administrador",
        role_id="role-admin",
        entity_id="entity-hub",
        department_id=None,
        manager_id=None,
        job_title=None,
        status="invited",
        is_external=False,
    )
    identity = FakeGoogleIdentity(
        sub="google-sub-admin",
        email="beatriz.luna@ameliahub.com",
        email_verified=True,
        full_name="Beatriz Luna",
        avatar_url=None,
        hosted_domain="ameliahub.com",
        is_internal=True,
    )
    user_repo = FakeUserRepository(users=[seeded_admin])
    use_case, _ = _build_use_case(user_repo, identity)

    result = await use_case.execute("fake-id-token")

    assert result.user.role_code == "administrador"
    assert result.user.status == "active"  # invited -> active tras el primer login
    assert user_repo.bound_calls == ["admin-1"]


@pytest.mark.asyncio
async def test_suspended_user_cannot_login():
    suspended = AuthenticatedUser(
        id="user-1",
        email="suspendido@ameliahub.com",
        full_name="Suspendido",
        avatar_url=None,
        role_code="empleado",
        role_id="role-empleado",
        entity_id=None,
        department_id=None,
        manager_id=None,
        job_title=None,
        status="suspended",
        is_external=False,
    )
    identity = FakeGoogleIdentity(
        sub="google-sub-3",
        email="suspendido@ameliahub.com",
        email_verified=True,
        full_name="Suspendido",
        avatar_url=None,
        hosted_domain="ameliahub.com",
        is_internal=True,
    )
    use_case, _ = _build_use_case(FakeUserRepository(users=[suspended]), identity)

    with pytest.raises(UserSuspendedError):
        await use_case.execute("fake-id-token")


@pytest.mark.asyncio
async def test_rejects_login_when_google_email_is_not_verified():
    """Defensa en profundidad (auditoría QA Fase 3): Google verifica la firma
    del id_token, pero `email_verified=false` no garantiza el titular del
    email — se rechaza ANTES de tocar el repositorio de usuarios."""
    identity = FakeGoogleIdentity(
        sub="google-sub-unverified",
        email="sin.verificar@ameliahub.com",
        email_verified=False,
        full_name="Sin Verificar",
        avatar_url=None,
        hosted_domain="ameliahub.com",
        is_internal=True,
    )
    user_repo = FakeUserRepository()
    use_case, _ = _build_use_case(user_repo, identity)

    with pytest.raises(EmailNotVerifiedError):
        await use_case.execute("fake-id-token")

    assert len(user_repo.users) == 0  # no se auto-provisiona con email sin verificar


@pytest.mark.asyncio
async def test_pending_invitation_takes_precedence_over_auto_provision():
    """
    Decisión de diseño (no explícita en el encargo): si hay una invitación
    pendiente para un email interno, se respeta su rol/entidad en vez de
    auto-provisionar como 'empleado' — permite a RRHH pre-asignar un rol
    distinto (p.ej. un futuro admin) antes del primer login.
    """
    invitation = PendingInvitation(
        id="inv-1",
        email="futura.admin@ameliahub.com",
        role_id="role-admin",
        role_code="administrador",
        entity_id="entity-hub",
    )
    identity = FakeGoogleIdentity(
        sub="google-sub-4",
        email="futura.admin@ameliahub.com",
        email_verified=True,
        full_name="Futura Admin",
        avatar_url=None,
        hosted_domain="ameliahub.com",
        is_internal=True,
    )
    use_case, _ = _build_use_case(FakeUserRepository(invitations=[invitation]), identity)

    result = await use_case.execute("fake-id-token")

    assert result.user.role_code == "administrador"


@pytest.mark.asyncio
async def test_existing_eager_user_wins_over_its_own_pending_invitation():
    """
    Regresión (design `rh-invitaciones-iconos-limpieza`, Área 1): el alta
    desde "Plantilla" (`staff.create_staff_member`) crea la fila `users` de
    forma EAGER *y* la fila `invitations` en la misma transacción — para ese
    mismo email conviven ambas desde el primer momento, no solo una
    invitación "pura" sin usuario todavía.

    `find_by_email` encuentra esa fila ANTES de mirar `invitations`, así que
    la rama `find_pending_invitation`/`create_user_from_invitation` NUNCA se
    ejecuta para altas hechas desde "Plantilla" — es deuda conocida
    (documentada, no una regresión de este cambio) y este test la fija como
    comportamiento esperado: gana el usuario ya existente, `invited` pasa a
    `active`, y la invitación sigue intacta (nadie la marca `accepted`).
    """
    invited_from_staff = AuthenticatedUser(
        id="user-1",
        email="nueva.empleada@ameliahub.com",
        full_name="Nueva Empleada",
        avatar_url=None,
        role_code="empleado",
        role_id="role-empleado",
        entity_id="entity-hub",
        department_id=None,
        manager_id=None,
        job_title=None,
        status="invited",
        is_external=False,
    )
    same_email_invitation = PendingInvitation(
        id="inv-1",
        email="nueva.empleada@ameliahub.com",
        role_id="role-empleado",
        role_code="empleado",
        entity_id="entity-hub",
    )
    identity = FakeGoogleIdentity(
        sub="google-sub-staff-alta",
        email="nueva.empleada@ameliahub.com",
        email_verified=True,
        full_name="Nueva Empleada",
        avatar_url=None,
        hosted_domain="ameliahub.com",
        is_internal=True,
    )
    user_repo = FakeUserRepository(
        users=[invited_from_staff], invitations=[same_email_invitation]
    )
    use_case, _ = _build_use_case(user_repo, identity)

    result = await use_case.execute("fake-id-token")

    assert result.user.id == "user-1"
    assert result.user.status == "active"  # invited -> active vía bind_google_login
    assert len(user_repo.users) == 1  # NO se creó un segundo usuario desde la invitación
    # La invitación sigue ahí tal cual — `create_user_from_invitation` (el
    # único que la marca 'accepted') nunca se llamó.
    assert "nueva.empleada@ameliahub.com" in user_repo.invitations
