"""
`GetAbsenceCalendarUseCase` — defensa en profundidad del scoping RGPD
(RF-A1): el router ya rechaza por rol (`INTERNAL_ROLES` en los exports,
`ADMIN_SOCIO` en `/calendar/all`), pero el use case NO debe confiar solo en
eso: si algún día se llama desde otro sitio (job, otro router), el guard
debe seguir vivo aquí.

Reglas (RF-A1, `sdd/ampliacion-v11-rrhh/design` § "RF-A1 · Contrato de API"):
- Admin/Socio: cualquier `user_id` (o ninguno -> global). Sin restricción.
- Empleado: `user_id` ausente -> se resuelve a su propio `requester_id`.
  `user_id` igual al propio -> OK. `user_id` de otro -> 403.
- Cualquier otro rol (p.ej. externo_invitado): 403 siempre.
"""

from datetime import date

import pytest

from src.features.absences.application.use_cases.get_absence_calendar import (
    GetAbsenceCalendarUseCase,
)
from src.features.absences.domain.errors import AbsenceForbiddenError


class _FakeRepositoryWithCalendar:
    """Solo implementa lo que este use case necesita — el resto de
    `IAbsenceRepository` no aplica aquí."""

    def __init__(self):
        self.called_with: dict | None = None

    async def list_calendar_entries(
        self, *, date_from: date, date_to: date, user_id=None
    ):
        self.called_with = {
            "date_from": date_from,
            "date_to": date_to,
            "user_id": user_id,
        }
        return []


@pytest.mark.parametrize("role", ["administrador", "socio"])
async def test_admin_and_socio_can_view_global_calendar_without_user_id(role):
    """Sin `user_id` -> global, comportamiento actual, no debe romperse."""
    repository = _FakeRepositoryWithCalendar()
    use_case = GetAbsenceCalendarUseCase(repository)

    result = await use_case.execute(
        requester_id="requester-1",
        requester_role=role,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
    )

    assert result == []
    assert repository.called_with == {
        "date_from": date(2026, 7, 1),
        "date_to": date(2026, 7, 31),
        "user_id": None,
    }


@pytest.mark.parametrize("role", ["administrador", "socio"])
async def test_admin_and_socio_can_view_any_users_calendar(role):
    """Con `user_id` de CUALQUIER otro usuario -> sin restricción."""
    repository = _FakeRepositoryWithCalendar()
    use_case = GetAbsenceCalendarUseCase(repository)

    result = await use_case.execute(
        requester_id="requester-1",
        requester_role=role,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
        user_id="other-user",
    )

    assert result == []
    assert repository.called_with["user_id"] == "other-user"


async def test_employee_without_user_id_resolves_to_own():
    repository = _FakeRepositoryWithCalendar()
    use_case = GetAbsenceCalendarUseCase(repository)

    await use_case.execute(
        requester_id="employee-1",
        requester_role="empleado",
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
    )

    assert repository.called_with["user_id"] == "employee-1"


async def test_employee_requesting_own_user_id_is_allowed():
    repository = _FakeRepositoryWithCalendar()
    use_case = GetAbsenceCalendarUseCase(repository)

    await use_case.execute(
        requester_id="employee-1",
        requester_role="empleado",
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
        user_id="employee-1",
    )

    assert repository.called_with["user_id"] == "employee-1"


async def test_employee_requesting_other_user_id_is_forbidden():
    repository = _FakeRepositoryWithCalendar()
    use_case = GetAbsenceCalendarUseCase(repository)

    with pytest.raises(AbsenceForbiddenError):
        await use_case.execute(
            requester_id="employee-1",
            requester_role="empleado",
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 31),
            user_id="other-user",
        )

    assert repository.called_with is None


async def test_externo_invitado_is_forbidden():
    """Defensa en profundidad: el router ya rechaza `externo_invitado` en
    los 3 endpoints (`INTERNAL_ROLES`/`ADMIN_SOCIO`), pero el use case no
    debe confiar solo en eso."""
    repository = _FakeRepositoryWithCalendar()
    use_case = GetAbsenceCalendarUseCase(repository)

    with pytest.raises(AbsenceForbiddenError):
        await use_case.execute(
            requester_id="ext-1",
            requester_role="externo_invitado",
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 31),
        )

    assert repository.called_with is None
