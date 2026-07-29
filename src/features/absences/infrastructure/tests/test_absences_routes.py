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


def test_externo_invitado_cannot_export_general_calendar_xlsx():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/calendar/export.xlsx",
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_employee_can_export_own_calendar_xlsx():
    """RF-A1: el Empleado ya puede exportar SU PROPIO calendario (antes era
    exclusivo de Admin/Socio)."""
    app.dependency_overrides[absences_dependencies.get_absence_calendar_use_case] = (
        lambda: _FakeAbsenceCalendarUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/calendar/export.xlsx?date_from=2026-07-01&date_to=2026-07-31",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_employee_cannot_export_other_users_calendar_xlsx():
    """RGPD (RF-A1): un Empleado pidiendo el `user_id` de OTRO recibe 403 —
    se usa el `GetAbsenceCalendarUseCase` REAL (con un repositorio fake) en
    vez de `_FakeAbsenceCalendarUseCase`, para ejercer el scoping fino de
    verdad end-to-end, no solo el gate de rol del router."""
    from src.features.absences.application.use_cases.get_absence_calendar import (
        GetAbsenceCalendarUseCase,
    )

    class _FakeRepoNeverReached:
        async def list_calendar_entries(self, *, date_from, date_to, user_id=None):
            raise AssertionError(
                "no debería llegar al repositorio: el 403 se lanza antes"
            )

    real_use_case = GetAbsenceCalendarUseCase(_FakeRepoNeverReached())

    app.dependency_overrides[absences_dependencies.get_absence_calendar_use_case] = (
        lambda: real_use_case
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/calendar/export.xlsx?date_from=2026-07-01&date_to=2026-07-31&user_id=other-user",
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


def test_externo_invitado_cannot_export_general_calendar_pdf():
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/calendar/export.pdf",
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_employee_can_export_own_calendar_pdf():
    app.dependency_overrides[absences_dependencies.get_absence_calendar_use_case] = (
        lambda: _FakeAbsenceCalendarUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/calendar/export.pdf?date_from=2026-07-01&date_to=2026-07-31",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_employee_cannot_export_other_users_calendar_pdf():
    from src.features.absences.application.use_cases.get_absence_calendar import (
        GetAbsenceCalendarUseCase,
    )

    class _FakeRepoNeverReached:
        async def list_calendar_entries(self, *, date_from, date_to, user_id=None):
            raise AssertionError(
                "no debería llegar al repositorio: el 403 se lanza antes"
            )

    real_use_case = GetAbsenceCalendarUseCase(_FakeRepoNeverReached())

    app.dependency_overrides[absences_dependencies.get_absence_calendar_use_case] = (
        lambda: real_use_case
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/calendar/export.pdf?date_from=2026-07-01&date_to=2026-07-31&user_id=other-user",
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


# --- RF-A1 (U2) — nombre de fichero y cabecera con empleado y periodo. ---


def test_slugify_name_strips_accents_lowercases_and_hyphenates():
    from src.features.absences.infrastructure.routes import _slugify_name

    assert _slugify_name("Ana García") == "ana-garcia"
    assert _slugify_name("José Ángel Núñez") == "jose-angel-nunez"
    assert _slugify_name("  Luis   Pérez  ") == "luis-perez"


class _FakeRepositoryWithFullName:
    def __init__(self, full_name: str | None):
        self._full_name = full_name

    async def find_user_full_name(self, user_id: str) -> str | None:
        return self._full_name


def test_export_xlsx_without_user_id_keeps_default_filename():
    """Sin `user_id`: nombre de fichero SIN CAMBIOS (comportamiento
    actual)."""
    app.dependency_overrides[absences_dependencies.get_absence_calendar_use_case] = (
        lambda: _FakeAbsenceCalendarUseCase()
    )
    app.dependency_overrides[absences_dependencies.get_absence_repository] = lambda: (
        _FakeRepositoryWithFullName("Ana García")
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
        'filename="calendario-ausencias-2026-07-01_2026-07-31.xlsx"'
        in response.headers["content-disposition"]
    )


def test_export_xlsx_with_user_id_uses_employee_slug_and_month_period():
    """Con `user_id` y rango = mes natural exacto: nombre con slug del
    nombre + periodo `YYYY-MM`."""
    app.dependency_overrides[absences_dependencies.get_absence_calendar_use_case] = (
        lambda: _FakeAbsenceCalendarUseCase()
    )
    app.dependency_overrides[absences_dependencies.get_absence_repository] = lambda: (
        _FakeRepositoryWithFullName("Ana García")
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/calendar/export.xlsx?date_from=2026-07-01&date_to=2026-07-31"
                "&user_id=user-1",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert (
        'filename="calendario-ausencias-ana-garcia-2026-07.xlsx"'
        in response.headers["content-disposition"]
    )


def test_export_xlsx_with_user_id_and_non_month_range_uses_from_to_period():
    """Con `user_id` pero rango que NO es un mes natural exacto: periodo
    `{from}_{to}`, igual que el export global."""
    app.dependency_overrides[absences_dependencies.get_absence_calendar_use_case] = (
        lambda: _FakeAbsenceCalendarUseCase()
    )
    app.dependency_overrides[absences_dependencies.get_absence_repository] = lambda: (
        _FakeRepositoryWithFullName("Ana García")
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/calendar/export.xlsx?date_from=2026-07-10&date_to=2026-07-20"
                "&user_id=user-1",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert (
        'filename="calendario-ausencias-ana-garcia-2026-07-10_2026-07-20.xlsx"'
        in response.headers["content-disposition"]
    )


def test_export_xlsx_with_user_id_but_no_full_name_falls_back_to_user_id():
    """Si `find_user_full_name` no encuentra al usuario (borrado o
    inexistente), el slug cae al `user_id` crudo en vez de reventar."""
    app.dependency_overrides[absences_dependencies.get_absence_calendar_use_case] = (
        lambda: _FakeAbsenceCalendarUseCase()
    )
    app.dependency_overrides[absences_dependencies.get_absence_repository] = lambda: (
        _FakeRepositoryWithFullName(None)
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/calendar/export.xlsx?date_from=2026-07-01&date_to=2026-07-31"
                "&user_id=deleted-user",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert (
        'filename="calendario-ausencias-deleted-user-2026-07.xlsx"'
        in response.headers["content-disposition"]
    )


def test_calendar_export_filename_sanitizes_raw_user_id_fallback():
    """SEC-2 (auditoría QA, severidad MEDIA): sin `subject_name` (usuario
    borrado/inexistente), el slug caía al `user_id` CRUDO, sin pasar por
    `_slugify_name` — ese valor va directo al header `Content-Disposition`.
    Un `user_id` con comillas/punto y coma rompe el parámetro `filename` e
    inyecta contenido en la misma cabecera HTTP. Solo Admin/Socio pueden
    mandar un `user_id` arbitrario, pero sigue siendo entrada sin sanear en
    una cabecera. El fallback debe sanearse igual que el nombre real."""
    from src.features.absences.infrastructure.routes import _calendar_export_filename

    filename = _calendar_export_filename(
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
        extension="xlsx",
        user_id='legit"; evil="x',
        subject_name=None,
    )

    assert '"' not in filename
    assert ";" not in filename
    assert filename == "calendario-ausencias-legit-evil-x-2026-07.xlsx"


def test_export_xlsx_with_unsafe_user_id_fallback_does_not_break_header():
    """Mismo caso que arriba, pero a nivel de cabecera HTTP real: el
    `Content-Disposition` de la respuesta no debe contener un segundo
    `filename=` inyectado ni comillas sin escapar."""
    app.dependency_overrides[absences_dependencies.get_absence_calendar_use_case] = (
        lambda: _FakeAbsenceCalendarUseCase()
    )
    app.dependency_overrides[absences_dependencies.get_absence_repository] = lambda: (
        _FakeRepositoryWithFullName(None)
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/calendar/export.xlsx",
                params={
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-31",
                    "user_id": 'legit"; evil="x',
                },
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    content_disposition = response.headers["content-disposition"]
    assert content_disposition.count('filename="') == 1
    assert (
        'filename="calendario-ausencias-legit-evil-x-2026-07.xlsx"'
        in content_disposition
    )


def test_export_pdf_with_user_id_uses_employee_slug_and_month_period():
    app.dependency_overrides[absences_dependencies.get_absence_calendar_use_case] = (
        lambda: _FakeAbsenceCalendarUseCase()
    )
    app.dependency_overrides[absences_dependencies.get_absence_repository] = lambda: (
        _FakeRepositoryWithFullName("Ana García")
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/absences/calendar/export.pdf?date_from=2026-07-01&date_to=2026-07-31"
                "&user_id=user-1",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert (
        'filename="calendario-ausencias-ana-garcia-2026-07.pdf"'
        in response.headers["content-disposition"]
    )
