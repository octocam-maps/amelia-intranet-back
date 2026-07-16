"""
Test route-level: cada usuario autenticado —cualquier rol— lee/marca SOLO
las suyas (el `user_id` viene del JWT, nunca de un parámetro). `jobs/run` es
exclusivo del admin — se rechaza en el BACKEND, no solo ocultando el botón.
Mismo patrón que `features/mailbox/infrastructure/tests/test_mailbox_routes.py`.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5999/nonexistent")

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from src.features.notifications.domain.errors import NotificationNotFoundError  # noqa: E402
from src.features.notifications.infrastructure import dependencies as notification_dependencies  # noqa: E402
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


def test_externo_invitado_can_read_their_own_notifications():
    """No hay ítem exclusivo en la matriz de permisos que lo prohíba — cada
    rol autenticado lee su propio buzón in-app."""

    class FakeListUseCase:
        async def execute(self, *, user_id, limit, before):
            from src.features.notifications.application.use_cases.list_notifications import (
                NotificationPage,
            )

            assert user_id == "user-1"
            return NotificationPage(items=[], next_before=None)

    app.dependency_overrides[notification_dependencies.get_list_notifications_use_case] = (
        lambda: FakeListUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/notifications",
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"items": [], "next_before": None}


def test_mark_read_returns_404_for_someone_elses_notification():
    class FakeMarkReadUseCase:
        async def execute(self, *, notification_id, user_id):
            raise NotificationNotFoundError("La notificación no existe.")

    app.dependency_overrides[notification_dependencies.get_mark_notification_read_use_case] = (
        lambda: FakeMarkReadUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.patch(
                "/notifications/not-mine/read",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_mark_read_returns_204_on_success():
    class FakeMarkReadUseCase:
        async def execute(self, *, notification_id, user_id):
            return None

    app.dependency_overrides[notification_dependencies.get_mark_notification_read_use_case] = (
        lambda: FakeMarkReadUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.patch(
                "/notifications/notif-1/read",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204


def test_empleado_cannot_run_notification_jobs():
    try:
        with TestClient(app) as client:
            response = client.post(
                "/notifications/jobs/run?job=daily",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_socio_can_read_their_own_notifications_but_not_run_jobs():
    """socio [migración 024] = igual que empleado -> su propio buzón
    in-app, nunca `jobs/run` (exclusivo del admin)."""

    class FakeListUseCase:
        async def execute(self, *, user_id, limit, before):
            from src.features.notifications.application.use_cases.list_notifications import (
                NotificationPage,
            )

            assert user_id == "user-1"
            return NotificationPage(items=[], next_before=None)

    app.dependency_overrides[notification_dependencies.get_list_notifications_use_case] = (
        lambda: FakeListUseCase()
    )
    try:
        with TestClient(app) as client:
            headers = {"Authorization": f"Bearer {_token_for('socio')}"}
            list_response = client.get("/notifications", headers=headers)
            job_response = client.post("/notifications/jobs/run?job=daily", headers=headers)
    finally:
        app.dependency_overrides.clear()

    assert list_response.status_code == 200
    assert job_response.status_code == 403


def test_admin_can_run_the_daily_notification_job():
    class FakeDailyJobUseCase:
        async def execute(self):
            return {"birthdays_notified": 1, "anniversaries_notified": 0}

    class FakeClockOutJobUseCase:
        async def execute(self):
            raise AssertionError("no debía llamarse — job=daily")

    app.dependency_overrides[
        notification_dependencies.get_run_daily_notification_job_use_case
    ] = lambda: FakeDailyJobUseCase()
    app.dependency_overrides[
        notification_dependencies.get_run_clock_out_notification_job_use_case
    ] = lambda: FakeClockOutJobUseCase()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/notifications/jobs/run?job=daily",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "job": "daily",
        "result": {"birthdays_notified": 1, "anniversaries_notified": 0},
    }


def test_jobs_run_rejects_an_unknown_job_value():
    try:
        with TestClient(app) as client:
            response = client.post(
                "/notifications/jobs/run?job=weekly",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
