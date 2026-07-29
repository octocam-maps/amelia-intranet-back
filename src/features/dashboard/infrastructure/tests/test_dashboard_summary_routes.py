"""
Test route-level: `GET /dashboard/summary` — el externo-invitado NO tiene
"Inicio" en la matriz de permisos (docs/permisos-roles.md: ❌) y debe
rechazarse en el BACKEND. `socio` [migración 024] = igual que empleado ->
mismos widgets, sin la bandeja/vista global del admin (eso lo decide el
propio caso de uso según `role`, no este router). Mismo patrón que
`features/dashboard/infrastructure/tests/test_dashboard_admin_metrics_routes.py`.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5999/nonexistent")

import pytest  # noqa: E402
from datetime import date  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from src.features.dashboard.domain.entities import (  # noqa: E402
    EmployeeDashboardSummary,
    TodayClockStatus,
    UpcomingHoliday,
)
from src.features.dashboard.infrastructure import dependencies as dashboard_dependencies  # noqa: E402
from src.shared.jwt import get_jwt_service  # noqa: E402


def _token_for(role: str) -> str:
    jwt_service = get_jwt_service()
    return jwt_service.create_access_token(
        {
            "sub": "user-1",
            "email": "user@ameliahub.com",
            "role": role,
            "entity_id": None,
            "is_external": role == "externo_invitado",
        }
    )


class _FakeSummaryUseCase:
    async def execute(self, *, user_id, role):
        return EmployeeDashboardSummary(
            vacation_balance=None,
            today_clock_status=TodayClockStatus(has_open_entry=False, worked_minutes_today=0),
            upcoming_holidays=[],
        )


@pytest.mark.parametrize("role", ["administrador", "empleado", "socio"])
def test_internal_roles_can_read_the_summary(role):
    app.dependency_overrides[dashboard_dependencies.get_dashboard_summary_use_case] = (
        lambda: _FakeSummaryUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/dashboard/summary", headers={"Authorization": f"Bearer {_token_for(role)}"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    # Ni admin ni socio devuelven los campos exclusivos del admin desde esta
    # fake (los añade `AdminDashboardSummary`, no `EmployeeDashboardSummary`).
    assert response.json()["pending_absence_requests"] is None


def test_externo_invitado_cannot_read_the_summary():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/dashboard/summary",
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_unauthenticated_request_is_rejected():
    with TestClient(app) as client:
        response = client.get("/dashboard/summary")

    assert response.status_code == 401


def test_upcoming_holidays_expose_the_real_scope():
    """El ámbito del festivo (nacional/autonómico/local/empresa) DEBE viajar en
    el contrato.

    La columna `holidays.scope` existe desde la migración `018`, y
    `HolidaysTable` del panel de administración ya la pinta con el dato real.
    `GET /dashboard/summary` era el único sitio que nunca la proyectó, y la
    tarjeta "Próximos festivos" del Inicio rellenaba el hueco **inventando** el
    ámbito: rotaba Nacional/Autonómico/Local por posición en la lista. Un
    festivo local aparecía como nacional según dónde cayera.
    """

    class _FakeWithScopedHolidays:
        async def execute(self, *, user_id, role):
            return EmployeeDashboardSummary(
                vacation_balance=None,
                today_clock_status=TodayClockStatus(has_open_entry=False, worked_minutes_today=0),
                upcoming_holidays=[
                    UpcomingHoliday(day=date(2026, 8, 15), name="Asunción", scope="nacional"),
                    UpcomingHoliday(day=date(2026, 9, 9), name="Fiesta local", scope="local"),
                    # `scope` es NULLable en la tabla: un festivo dado de alta a
                    # mano puede no tenerlo, y el contrato debe permitirlo.
                    UpcomingHoliday(day=date(2026, 10, 12), name="Sin ámbito", scope=None),
                ],
            )

    app.dependency_overrides[dashboard_dependencies.get_dashboard_summary_use_case] = (
        lambda: _FakeWithScopedHolidays()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/dashboard/summary", headers={"Authorization": f"Bearer {_token_for('empleado')}"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    holidays = response.json()["upcoming_holidays"]
    assert [h["scope"] for h in holidays] == ["nacional", "local", None]
