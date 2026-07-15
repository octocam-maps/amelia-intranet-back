"""
Test route-level: el externo-invitado NO tiene "Control horario" en la
matriz de permisos (docs/permisos-roles.md: ❌) — debe rechazarse en el
BACKEND, no solo ocultarse del navbar. Se ejercitan las rutas reales de
FastAPI (mismo patrón que `features/auth/infrastructure/tests/test_auth_routes.py`):
el `JWTService` es el real (comparte secreto con `get_current_user`), solo
se sustituye el repositorio por un fake vía `app.dependency_overrides`.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5999/nonexistent")

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from src.features.time_clock.infrastructure import dependencies as time_clock_dependencies  # noqa: E402
from src.shared.jwt import get_jwt_service  # noqa: E402


def _token_for(role: str) -> str:
    jwt_service = get_jwt_service()
    return jwt_service.create_access_token(
        {"sub": "user-1", "email": "user@ameliahub.com", "role": role, "entity_id": None, "is_external": role == "externo_invitado"}
    )


def test_externo_invitado_cannot_list_time_clock_entries():
    response = None
    try:
        with TestClient(app) as client:
            response = client.get(
                "/time-clock/entries", headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_employee_can_list_their_own_time_clock_entries():
    class FakeListUseCase:
        async def execute(self, **kwargs):
            return []

    app.dependency_overrides[time_clock_dependencies.get_list_time_clock_entries_use_case] = (
        lambda: FakeListUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/time-clock/entries", headers={"Authorization": f"Bearer {_token_for('empleado')}"}
            )
            assert response.status_code == 200
            assert response.json() == {"entries": []}
    finally:
        app.dependency_overrides.clear()


def test_externo_invitado_cannot_read_current_clock_status():
    response = None
    try:
        with TestClient(app) as client:
            response = client.get(
                "/time-clock/current",
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_externo_invitado_cannot_export_time_clock_entries_xlsx():
    """El externo-invitado sigue rechazado — no tiene "Control horario" en la
    matriz de permisos, sin importar el alcance."""
    response = None
    try:
        with TestClient(app) as client:
            response = client.get(
                "/time-clock/entries/export.xlsx",
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_admin_can_export_time_clock_entries_xlsx():
    class FakeExportUseCase:
        async def execute(self, **kwargs):
            self.received_kwargs = kwargs
            return []

    use_case = FakeExportUseCase()
    app.dependency_overrides[time_clock_dependencies.get_export_time_clock_entries_use_case] = (
        lambda: use_case
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/time-clock/entries/export.xlsx",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
            assert response.status_code == 200
            assert response.headers["content-type"] == (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            assert "attachment; filename=" in response.headers["content-disposition"]
            assert ".xlsx" in response.headers["content-disposition"]
            # RGPD: el admin recibe el informe de TODA la plantilla, no
            # acotado a un `user_id` (el router no lo restringe).
            assert use_case.received_kwargs["user_id"] is None
    finally:
        app.dependency_overrides.clear()


def test_employee_can_export_only_their_own_time_clock_entries_xlsx():
    """RGPD: un empleado SÍ puede generar el XLSX, pero el router debe pasar
    `user_id=current_user["sub"]` al caso de uso — nunca `None` (que
    devolvería toda la plantilla) ni el `user_id` de otra persona."""

    class FakeExportUseCase:
        async def execute(self, **kwargs):
            self.received_kwargs = kwargs
            return []

    use_case = FakeExportUseCase()
    app.dependency_overrides[time_clock_dependencies.get_export_time_clock_entries_use_case] = (
        lambda: use_case
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/time-clock/entries/export.xlsx",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
            assert response.status_code == 200
            assert use_case.received_kwargs["user_id"] == "user-1"
    finally:
        app.dependency_overrides.clear()


def test_employee_can_read_current_clock_status():
    from datetime import datetime, timezone

    class FakeLiveStatusUseCase:
        async def execute(self, **kwargs):
            from src.features.time_clock.application.results import (
                LiveClockStatusResult,
                OpenEntryStatus,
            )

            return LiveClockStatusResult(
                open_entry=OpenEntryStatus(
                    id="entry-1",
                    clock_in=datetime(2026, 7, 9, 9, 0, tzinfo=timezone.utc),
                    on_break=False,
                ),
                week_worked_minutes=120,
                expected_weekly_minutes=2400,
            )

    app.dependency_overrides[time_clock_dependencies.get_live_status_use_case] = (
        lambda: FakeLiveStatusUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/time-clock/current",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["open_entry"]["id"] == "entry-1"
            assert body["expected_weekly_minutes"] == 2400
    finally:
        app.dependency_overrides.clear()
