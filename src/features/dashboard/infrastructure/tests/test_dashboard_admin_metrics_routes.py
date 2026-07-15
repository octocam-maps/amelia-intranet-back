"""
Test route-level: `/dashboard/admin/metrics` es EXCLUSIVO del administrador
(docs/permisos-roles.md § Administración) — empleado y externo-invitado
deben recibir 403, nunca 404 (escribir la URL a mano no debe dar acceso).
Mismo patrón que `features/team/infrastructure/tests/test_team_routes.py`.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5999/nonexistent")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from src.features.dashboard.domain.entities import (  # noqa: E402
    AdminDashboardMetrics,
    AdminMetricsKPIs,
    AttendanceRadarItem,
    MetricsTrends,
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


class _FakeAdminMetricsUseCase:
    def __init__(self):
        self.received_kwargs = None

    async def execute(self, *, entity_id=None, department_id=None, period_days=14):
        self.received_kwargs = {
            "entity_id": entity_id,
            "department_id": department_id,
            "period_days": period_days,
        }
        return AdminDashboardMetrics(
            kpis=AdminMetricsKPIs(
                absent_today=1, pending_approvals=2, clocked_in_now=3, punctuality_pct=90
            ),
            trends=MetricsTrends(absences=[1, 0], clocked_in=[3, 4], punctuality=[100, 80]),
            attendance_radar=[
                AttendanceRadarItem(
                    user_id="user-2",
                    full_name="Ana García",
                    avatar_url=None,
                    kind="late_in",
                    value_minutes=45,
                    detail="Entrada 09:45 (media)",
                )
            ],
        )


@pytest.mark.parametrize("role", ["empleado", "externo_invitado"])
def test_non_admin_roles_are_rejected_with_403(role):
    with TestClient(app) as client:
        response = client.get(
            "/dashboard/admin/metrics", headers={"Authorization": f"Bearer {_token_for(role)}"}
        )

    assert response.status_code == 403


def test_unauthenticated_request_is_rejected_with_401():
    with TestClient(app) as client:
        response = client.get("/dashboard/admin/metrics")

    assert response.status_code == 401


def test_administrador_gets_the_full_metrics_payload():
    use_case = _FakeAdminMetricsUseCase()
    app.dependency_overrides[dashboard_dependencies.get_admin_metrics_use_case] = lambda: use_case
    try:
        with TestClient(app) as client:
            response = client.get(
                "/dashboard/admin/metrics",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["kpis"] == {
        "absent_today": 1,
        "pending_approvals": 2,
        "clocked_in_now": 3,
        "punctuality_pct": 90,
    }
    assert body["trends"] == {
        "absences": [1, 0],
        "clocked_in": [3, 4],
        "punctuality": [100, 80],
    }
    assert body["attendance_radar"] == [
        {
            "user_id": "user-2",
            "full_name": "Ana García",
            "avatar_url": None,
            "kind": "late_in",
            "value_minutes": 45,
            "detail": "Entrada 09:45 (media)",
        }
    ]


def test_query_params_are_forwarded_to_the_use_case():
    use_case = _FakeAdminMetricsUseCase()
    app.dependency_overrides[dashboard_dependencies.get_admin_metrics_use_case] = lambda: use_case
    try:
        with TestClient(app) as client:
            response = client.get(
                "/dashboard/admin/metrics"
                "?entity_id=11111111-1111-1111-1111-111111111111"
                "&department_id=22222222-2222-2222-2222-222222222222"
                "&period_days=7",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert use_case.received_kwargs == {
        "entity_id": "11111111-1111-1111-1111-111111111111",
        "department_id": "22222222-2222-2222-2222-222222222222",
        "period_days": 7,
    }


def test_period_days_out_of_range_is_rejected_with_422():
    with TestClient(app) as client:
        response = client.get(
            "/dashboard/admin/metrics?period_days=0",
            headers={"Authorization": f"Bearer {_token_for('administrador')}"},
        )

    assert response.status_code == 422
