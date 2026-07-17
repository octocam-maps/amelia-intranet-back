"""
`GetAbsenceCalendarUseCase` — defensa en profundidad del rol permitido
(administrador + socio, migración 024). El router ya rechaza con
`require_role`, pero el use case NO debe confiar solo en eso: si algún día
se llama desde otro sitio (job, otro router), el guard debe seguir vivo aquí.
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

    async def list_calendar_entries(self, *, date_from: date, date_to: date):
        self.called_with = {"date_from": date_from, "date_to": date_to}
        return []


@pytest.mark.parametrize("role", ["administrador", "socio"])
async def test_admin_and_socio_can_view_general_calendar(role):
    repository = _FakeRepositoryWithCalendar()
    use_case = GetAbsenceCalendarUseCase(repository)

    result = await use_case.execute(
        requester_role=role, date_from=date(2026, 7, 1), date_to=date(2026, 7, 31)
    )

    assert result == []
    assert repository.called_with == {"date_from": date(2026, 7, 1), "date_to": date(2026, 7, 31)}


@pytest.mark.parametrize("role", ["empleado", "externo_invitado"])
async def test_other_roles_cannot_view_general_calendar(role):
    repository = _FakeRepositoryWithCalendar()
    use_case = GetAbsenceCalendarUseCase(repository)

    with pytest.raises(AbsenceForbiddenError):
        await use_case.execute(
            requester_role=role, date_from=date(2026, 7, 1), date_to=date(2026, 7, 31)
        )

    assert repository.called_with is None
