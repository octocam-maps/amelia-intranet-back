"""
Test route-level: el externo-invitado NO tiene "Ausencias" en la matriz de
permisos (docs/permisos-roles.md: ❌) — debe rechazarse en el BACKEND, no
solo ocultarse del navbar. Mismo patrón que
`features/time_clock/infrastructure/tests/test_time_clock_routes.py`.
"""

import os
from datetime import date
from types import SimpleNamespace
from typing import Optional

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5999/nonexistent")

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from src.features.absences.infrastructure import dependencies as absences_dependencies  # noqa: E402
from src.shared.jwt import get_jwt_service  # noqa: E402


def _token_for(role: str) -> str:
    jwt_service = get_jwt_service()
    return jwt_service.create_access_token(
        {"sub": "user-1", "email": "user@ameliahub.com", "role": role, "entity_id": None, "is_external": role == "externo_invitado"}
    )


def test_externo_invitado_cannot_list_absence_types():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/types", headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_externo_invitado_cannot_open_pending_tray():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/requests/pending",
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_employee_can_list_absence_types():
    class FakeListTypesUseCase:
        async def execute(self):
            return []

    app.dependency_overrides[absences_dependencies.get_list_absence_types_use_case] = (
        lambda: FakeListTypesUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/types", headers={"Authorization": f"Bearer {_token_for('empleado')}"}
            )
            assert response.status_code == 200
            assert response.json() == {"types": []}
    finally:
        app.dependency_overrides.clear()


def test_employee_cannot_open_pending_tray():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/requests/pending",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_employee_cannot_manage_absence_types():
    """"Tipos de ausencia" es exclusivo del admin (docs/permisos-roles.md §
    "Tipos de ausencia") — ni el listado de gestión ni el CRUD son
    accesibles para el empleado."""
    try:
        with TestClient(app) as client:
            headers = {"Authorization": f"Bearer {_token_for('empleado')}"}
            admin_list_response = client.get("/absences/types/admin", headers=headers)
            create_response = client.post(
                "/absences/types", json={"code": "x", "name": "X"}, headers=headers
            )
            update_response = client.patch(
                "/absences/types/type-1", json={"name": "x"}, headers=headers
            )
    finally:
        app.dependency_overrides.clear()

    assert admin_list_response.status_code == 403
    assert create_response.status_code == 403
    assert update_response.status_code == 403


def test_admin_can_create_an_absence_type():
    class FakeCreateTypeUseCase:
        async def execute(self, **kwargs):
            class _Type:
                id = "type-1"
                code = kwargs["code"]
                name = kwargs["name"]
                is_paid = kwargs["is_paid"]
                affects_balance = kwargs["affects_balance"]
                default_entitled_days = kwargs["default_entitled_days"]
                color = kwargs["color"]
                is_active = True
                requires_approval = kwargs.get("requires_approval", True)
                requires_justification = kwargs.get("requires_justification", False)
                max_days_per_year = kwargs.get("max_days_per_year")

            return _Type()

    app.dependency_overrides[absences_dependencies.get_create_absence_type_use_case] = (
        lambda: FakeCreateTypeUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/absences/types",
                json={"code": "excedencia", "name": "Excedencia"},
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
            assert response.status_code == 201
            assert response.json()["code"] == "excedencia"
    finally:
        app.dependency_overrides.clear()


def test_admin_can_list_all_absence_types_including_inactive():
    class FakeListAllTypesUseCase:
        async def execute(self):
            return []

    app.dependency_overrides[absences_dependencies.get_list_all_absence_types_use_case] = (
        lambda: FakeListAllTypesUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/types/admin",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
            assert response.status_code == 200
            assert response.json() == {"types": []}
    finally:
        app.dependency_overrides.clear()


# --- Calendario general de la plantilla (LOTE 4) — exclusivo del admin. ---


def _calendar_entry_kwargs(**overrides) -> dict:
    kwargs = dict(
        request_id="req-1",
        user_id="user-1",
        user_full_name="Ana García",
        absence_type_id="type-vacaciones",
        absence_type_name="Vacaciones",
        absence_type_color="#00D170",
        start_date=date(2026, 7, 20),
        end_date=date(2026, 7, 24),
        days_count=5.0,
        status="approved",
    )
    kwargs.update(overrides)
    return kwargs


class _FakeAbsenceCalendarUseCase:
    """Devuelve objetos con atributos (no dicts) — los mappers acceden con
    `entry.request_id`, no `entry["request_id"]`."""

    def __init__(self, rows: Optional[list[dict]] = None):
        self._rows = rows if rows is not None else [_calendar_entry_kwargs()]

    async def execute(self, **kwargs):
        return [SimpleNamespace(**row) for row in self._rows]


def test_employee_cannot_view_general_calendar():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/calendar/all",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_externo_invitado_cannot_view_general_calendar():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/calendar/all",
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_admin_can_view_general_calendar():
    app.dependency_overrides[absences_dependencies.get_absence_calendar_use_case] = (
        lambda: _FakeAbsenceCalendarUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/calendar/all?date_from=2026-07-01&date_to=2026-07-31",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["entries"][0]["user_full_name"] == "Ana García"
    assert body["entries"][0]["absence_type_name"] == "Vacaciones"


def test_socio_can_view_general_calendar():
    """socio [migración 024]: visión global del calendario de vacaciones,
    igual que el admin — RBAC real vía `require_role`, no un ítem oculto del
    navbar."""
    app.dependency_overrides[absences_dependencies.get_absence_calendar_use_case] = (
        lambda: _FakeAbsenceCalendarUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/calendar/all?date_from=2026-07-01&date_to=2026-07-31",
                headers={"Authorization": f"Bearer {_token_for('socio')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["entries"][0]["user_full_name"] == "Ana García"


def test_employee_cannot_export_general_calendar_xlsx():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/calendar/export.xlsx",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_admin_can_export_general_calendar_xlsx():
    app.dependency_overrides[absences_dependencies.get_absence_calendar_use_case] = (
        lambda: _FakeAbsenceCalendarUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/calendar/export.xlsx?date_from=2026-07-01&date_to=2026-07-31",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert (
        response.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert len(response.content) > 0


def test_socio_can_export_general_calendar_xlsx():
    app.dependency_overrides[absences_dependencies.get_absence_calendar_use_case] = (
        lambda: _FakeAbsenceCalendarUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/calendar/export.xlsx?date_from=2026-07-01&date_to=2026-07-31",
                headers={"Authorization": f"Bearer {_token_for('socio')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_employee_cannot_export_general_calendar_pdf():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/calendar/export.pdf",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_admin_can_export_general_calendar_pdf():
    app.dependency_overrides[absences_dependencies.get_absence_calendar_use_case] = (
        lambda: _FakeAbsenceCalendarUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/calendar/export.pdf?date_from=2026-07-01&date_to=2026-07-31",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    # Magic bytes de un PDF válido — no parseamos el contenido byte a byte.
    assert response.content.startswith(b"%PDF")


def test_socio_can_export_general_calendar_pdf():
    app.dependency_overrides[absences_dependencies.get_absence_calendar_use_case] = (
        lambda: _FakeAbsenceCalendarUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/calendar/export.pdf?date_from=2026-07-01&date_to=2026-07-31",
                headers={"Authorization": f"Bearer {_token_for('socio')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_socio_cannot_approve_absence_requests():
    """socio = igual que empleado + calendario global — NO hereda el resto
    de "Administración" (aprobar ausencias sigue exclusivo del admin)."""
    try:
        with TestClient(app) as client:
            response = client.post(
                "/absences/requests/req-1/review",
                json={"decision": "approved"},
                headers={"Authorization": f"Bearer {_token_for('socio')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_socio_cannot_manage_absence_types():
    """"Tipos de ausencia" sigue exclusivo del admin — socio no lo hereda."""
    try:
        with TestClient(app) as client:
            headers = {"Authorization": f"Bearer {_token_for('socio')}"}
            admin_list_response = client.get("/absences/types/admin", headers=headers)
            create_response = client.post(
                "/absences/types", json={"code": "x", "name": "X"}, headers=headers
            )
    finally:
        app.dependency_overrides.clear()

    assert admin_list_response.status_code == 403
    assert create_response.status_code == 403


def test_socio_cannot_open_pending_tray():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/requests/pending",
                headers={"Authorization": f"Bearer {_token_for('socio')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
