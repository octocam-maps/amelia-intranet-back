"""
Test route-level: `/team/directory` y `/team/vacation-calendar` son
visibles para los 3 roles (docs/permisos-roles.md § Equipo, sin ❌) — a
diferencia de `dashboard`/`absences`, aquí no hay ningún rol a rechazar.
Mismo patrón que `features/absences/infrastructure/tests/test_absences_routes.py`.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5999/nonexistent")

from datetime import date  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from src.features.team.domain.entities import (  # noqa: E402
    TeamBirthday,
    TeamMember,
    VacationCalendarEntry,
)
from src.features.team.infrastructure import dependencies as team_dependencies  # noqa: E402
from src.shared.jwt import get_jwt_service  # noqa: E402

_ROLES = ("administrador", "empleado", "externo_invitado")


def _token_for(role: str) -> str:
    jwt_service = get_jwt_service()
    return jwt_service.create_access_token(
        {"sub": "user-1", "email": "user@ameliahub.com", "role": role, "entity_id": None, "is_external": role == "externo_invitado"}
    )


class _FakeDirectoryUseCase:
    async def execute(self):
        return [
            TeamMember(
                id="user-1",
                full_name="Ana García",
                job_title="Técnica de RRHH",
                entity_code="hub",
                entity_name="Amelia Hub",
                phone="+34600000000",
                email="ana.garcia@ameliahub.com",
                avatar_url=None,
            )
        ]


class _FakeVacationCalendarUseCase:
    async def execute(self, *, year: int, month: int):
        return [
            VacationCalendarEntry(
                user_id="user-1",
                full_name="Ana García",
                start_date=date(2026, 7, 20),
                end_date=date(2026, 7, 24),
            )
        ]


@pytest.mark.parametrize("role", _ROLES)
def test_any_authenticated_role_can_read_directory(role):
    app.dependency_overrides[team_dependencies.get_list_team_directory_use_case] = (
        lambda: _FakeDirectoryUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/team/directory", headers={"Authorization": f"Bearer {_token_for(role)}"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_directory_response_never_leaks_sensitive_fields():
    app.dependency_overrides[team_dependencies.get_list_team_directory_use_case] = (
        lambda: _FakeDirectoryUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/team/directory",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    member = response.json()["members"][0]
    sensitive_fields = {"dni_nif", "iban", "address", "social_security_number", "birth_date"}
    assert sensitive_fields.isdisjoint(member.keys())


@pytest.mark.parametrize("role", _ROLES)
def test_any_authenticated_role_can_read_vacation_calendar(role):
    app.dependency_overrides[team_dependencies.get_vacation_calendar_use_case] = (
        lambda: _FakeVacationCalendarUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/team/vacation-calendar?month=2026-07",
                headers={"Authorization": f"Bearer {_token_for(role)}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "entries": [
            {
                "user_id": "user-1",
                "full_name": "Ana García",
                "start_date": "2026-07-20",
                "end_date": "2026-07-24",
            }
        ]
    }


def test_vacation_calendar_rejects_malformed_month():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/team/vacation-calendar?month=2026-13",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_unauthenticated_request_is_rejected():
    with TestClient(app) as client:
        response = client.get("/team/directory")

    assert response.status_code == 401


class _FakeBirthdaysUseCase:
    async def execute(self, *, days: int = 7):
        return [
            TeamBirthday(
                user_id="user-1",
                full_name="Ana García",
                avatar_url=None,
                day=15,
                month=7,
                is_today=True,
            )
        ]


@pytest.mark.parametrize("role", _ROLES)
def test_any_authenticated_role_can_read_birthdays(role):
    app.dependency_overrides[team_dependencies.get_upcoming_birthdays_use_case] = (
        lambda: _FakeBirthdaysUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/team/birthdays", headers={"Authorization": f"Bearer {_token_for(role)}"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "birthdays": [
            {
                "user_id": "user-1",
                "full_name": "Ana García",
                "avatar_url": None,
                "day": 15,
                "month": 7,
                "is_today": True,
            }
        ]
    }
    assert "birth_date" not in body["birthdays"][0]


def test_birthdays_rejects_non_numeric_days():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/team/birthdays?days=abc",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_birthdays_rejects_out_of_range_days():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/team/birthdays?days=0",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_birthdays_unauthenticated_request_is_rejected():
    with TestClient(app) as client:
        response = client.get("/team/birthdays")

    assert response.status_code == 401
