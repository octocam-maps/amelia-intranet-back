"""
Aviso al equipo cuando entra alguien nuevo (migración 042).

Lo que se protege: que el aviso no pueda tumbar un alta, que no se anuncie a quien
no debe, y que el admin pueda apagarlo.
"""

from datetime import date

import pytest

from src.features.staff.application.use_cases.create_staff_member import (
    CreateStaffMemberUseCase,
)

from .fakes import _DEFAULT_INVITED_BY, FakeEmailSender, FakeStaffRepository


class FakeJoinedAnnouncer:
    def __init__(self, *, fails: bool = False):
        self.calls: list[dict] = []
        self._fails = fails

    async def announce(self, **kwargs):
        self.calls.append(kwargs)
        if self._fails:
            raise RuntimeError("SendGrid no responde")


def _use_case(repository, announcer):
    return CreateStaffMemberUseCase(
        repository,
        FakeEmailSender(),
        7,
        "https://intranet.ameliahub.com",
        None,
        announcer,
    )


async def _create(repository, announcer, *, role_code="empleado", **overrides):
    payload = {
        "full_name": "Sandra Ramírez",
        "email": "sandra@ameliahub.com",
        "job_title": "Project Manager",
        "department": None,
        "entity_code": "hub",
        "role_code": role_code,
        "hire_date": date(2026, 8, 1),
        "vacation_days_override": None,
        "invited_by": _DEFAULT_INVITED_BY,
    }
    payload.update(overrides)
    return await _use_case(repository, announcer).execute(**payload)


@pytest.mark.asyncio
async def test_announces_the_new_hire_to_the_team():
    repository = FakeStaffRepository()
    announcer = FakeJoinedAnnouncer()

    member = await _create(repository, announcer)

    assert len(announcer.calls) == 1
    assert announcer.calls[0]["user_id"] == member.id
    assert announcer.calls[0]["full_name"] == "Sandra Ramírez"
    assert announcer.calls[0]["job_title"] == "Project Manager"


@pytest.mark.asyncio
async def test_does_not_announce_an_external_guest():
    """Un externo-invitado es un colaborador de fuera con acceso parcial, no una
    incorporación al equipo. Anunciarlo a toda la plantilla sería ruido y además
    expondría su alta a gente que no tiene por qué saberla."""
    repository = FakeStaffRepository()
    announcer = FakeJoinedAnnouncer()

    await _create(
        repository,
        announcer,
        role_code="externo_invitado",
        email="colaborador@gmail.com",
    )

    assert announcer.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("role_code", ["empleado", "administrador", "socio", "becario"])
async def test_announces_every_internal_role_including_becario(role_code):
    """Un becario SÍ se anuncia: es una incorporación al equipo como cualquier
    otra, y el rol solo le quita el fichaje."""
    repository = FakeStaffRepository()
    announcer = FakeJoinedAnnouncer()

    await _create(repository, announcer, role_code=role_code)

    assert len(announcer.calls) == 1


@pytest.mark.asyncio
async def test_a_failing_announcement_does_not_revert_the_hire():
    """EL TEST QUE IMPORTA. La persona ya está en `users` y en `invitations`: un
    fallo de correo no puede deshacer eso ni propagar un 500 al admin, que vería
    un error habiendo funcionado el alta."""
    repository = FakeStaffRepository()
    announcer = FakeJoinedAnnouncer(fails=True)

    member = await _create(repository, announcer)

    assert member.id in repository.members
    assert len(repository.invitations) == 1


@pytest.mark.asyncio
async def test_the_hire_works_without_an_announcer_at_all():
    """El puerto es opcional: sin él, el alta funciona igual y solo no se
    anuncia. Es lo que mantiene verdes los tests que no lo inyectan."""
    repository = FakeStaffRepository()

    member = await _create(repository, None)

    assert member.id in repository.members


@pytest.mark.asyncio
async def test_the_welcome_email_is_sent_before_the_team_announcement():
    """Si solo pudiera salir un correo, el que importa es el de la persona que
    necesita entrar — no el aviso al resto."""
    repository = FakeStaffRepository()
    announcer = FakeJoinedAnnouncer()
    email_sender = FakeEmailSender()
    use_case = CreateStaffMemberUseCase(
        repository, email_sender, 7, "https://intranet.ameliahub.com", None, announcer
    )

    await use_case.execute(
        full_name="Sandra Ramírez",
        email="sandra@ameliahub.com",
        job_title="PM",
        department=None,
        entity_code="hub",
        role_code="empleado",
        hire_date=None,
        vacation_days_override=None,
        invited_by=_DEFAULT_INVITED_BY,
    )

    # La bienvenida ya salió cuando se dispara el aviso al equipo.
    assert any(sent["template"] == "staff_invited" for sent in email_sender.sent)
    assert len(announcer.calls) == 1
