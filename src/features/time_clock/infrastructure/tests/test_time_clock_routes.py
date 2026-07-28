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
    from src.features.time_clock.application.use_cases.list_time_clock_entries import (
        TimeClockEntryPage,
    )

    class FakeListUseCase:
        async def execute(self, **kwargs):
            self.received_kwargs = kwargs
            return TimeClockEntryPage(items=[], total=0)

    use_case = FakeListUseCase()
    app.dependency_overrides[time_clock_dependencies.get_list_time_clock_entries_use_case] = (
        lambda: use_case
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/time-clock/entries", headers={"Authorization": f"Bearer {_token_for('empleado')}"}
            )
            assert response.status_code == 200
            # X1 (Lote 1): la respuesta pasa a incluir el contrato de
            # paginación — `limit`/`offset` traen los defaults del router.
            assert response.json() == {"entries": [], "total": 0, "limit": 50, "offset": 0}
            assert use_case.received_kwargs["limit"] == 50
            assert use_case.received_kwargs["offset"] == 0
    finally:
        app.dependency_overrides.clear()


def test_employee_can_paginate_their_own_time_clock_entries():
    """X1 (Lote 1): `limit`/`offset` de la query se propagan al caso de uso
    y vuelven en la respuesta para que el frontend construya el paginador."""
    from src.features.time_clock.application.use_cases.list_time_clock_entries import (
        TimeClockEntryPage,
    )

    class FakeListUseCase:
        async def execute(self, **kwargs):
            self.received_kwargs = kwargs
            return TimeClockEntryPage(items=[], total=137)

    use_case = FakeListUseCase()
    app.dependency_overrides[time_clock_dependencies.get_list_time_clock_entries_use_case] = (
        lambda: use_case
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/time-clock/entries?limit=20&offset=40",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["total"] == 137
            assert body["limit"] == 20
            assert body["offset"] == 40
            assert use_case.received_kwargs["limit"] == 20
            assert use_case.received_kwargs["offset"] == 40
    finally:
        app.dependency_overrides.clear()


def test_employee_cannot_filter_time_clock_entries_by_another_user_id():
    """RGPD: aunque el query param `user_id` viaja igual para admin y
    empleado, el USE CASE (no el router) es quien decide el alcance según el
    rol — el router solo lo reenvía. Este test cubre que el router de verdad
    reenvía `user_id` para que ese guard pueda aplicarse."""
    from src.features.time_clock.domain.errors import TimeClockForbiddenError

    class FakeListUseCase:
        async def execute(self, **kwargs):
            if kwargs["target_user_id"] and kwargs["target_user_id"] != kwargs["requester_id"]:
                raise TimeClockForbiddenError("No puedes ver el fichaje de otro usuario.")
            return None

    app.dependency_overrides[time_clock_dependencies.get_list_time_clock_entries_use_case] = (
        lambda: FakeListUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/time-clock/entries?user_id=user-2",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
            assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_admin_can_filter_time_clock_entries_by_multiple_user_ids():
    """Multi-selector de personas (Lote 2): el router parsea `user_ids`
    (CSV) y lo reenvía como `target_user_ids` — el guard RGPD real vive en
    el use case, aquí solo se cubre que el router de verdad lo propaga."""
    from src.features.time_clock.application.use_cases.list_time_clock_entries import (
        TimeClockEntryPage,
    )

    class FakeListUseCase:
        async def execute(self, **kwargs):
            self.received_kwargs = kwargs
            return TimeClockEntryPage(items=[], total=0)

    use_case = FakeListUseCase()
    app.dependency_overrides[time_clock_dependencies.get_list_time_clock_entries_use_case] = (
        lambda: use_case
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/time-clock/entries?user_ids=user-2,user-3",
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
            assert response.status_code == 200
            assert use_case.received_kwargs["target_user_ids"] == ["user-2", "user-3"]
    finally:
        app.dependency_overrides.clear()


def test_employee_cannot_filter_time_clock_entries_by_multiple_user_ids():
    """RGPD: aunque el query param viaja igual para admin y empleado, el USE
    CASE es quien decide el alcance según el rol — mismo patrón que
    `test_employee_cannot_filter_time_clock_entries_by_another_user_id`,
    aquí cubriendo `user_ids` (multi-selector) en vez del `user_id` singular."""
    from src.features.time_clock.domain.errors import TimeClockForbiddenError

    class FakeListUseCase:
        async def execute(self, **kwargs):
            ids = kwargs.get("target_user_ids")
            if ids and (len(ids) > 1 or ids[0] != kwargs["requester_id"]):
                raise TimeClockForbiddenError("No puedes ver el fichaje de otro usuario.")
            return None

    app.dependency_overrides[time_clock_dependencies.get_list_time_clock_entries_use_case] = (
        lambda: FakeListUseCase()
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/time-clock/entries?user_ids=user-2,user-3",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


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


def test_employee_cannot_add_a_note_to_a_time_clock_entry():
    """B-2b: solo el admin puede dejar incidencias — el empleado se rechaza
    en el BACKEND, no solo ocultando el botón en el frontend."""
    response = None
    try:
        with TestClient(app) as client:
            response = client.post(
                "/time-clock/entries/entry-1/notes",
                json={"body": "Intento no autorizado."},
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_admin_can_add_a_note_to_a_time_clock_entry():
    from datetime import datetime, timezone

    from src.features.time_clock.domain.entities import TimeClockEntryNote

    class FakeAddNoteUseCase:
        async def execute(self, **kwargs):
            self.received_kwargs = kwargs
            return TimeClockEntryNote(
                id="note-1",
                entry_id=kwargs["entry_id"],
                author_id=kwargs["author_id"],
                body=kwargs["body"],
                created_at=datetime(2026, 7, 9, 10, 0, tzinfo=timezone.utc),
            )

    use_case = FakeAddNoteUseCase()
    app.dependency_overrides[time_clock_dependencies.get_add_time_clock_entry_note_use_case] = (
        lambda: use_case
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/time-clock/entries/entry-1/notes",
                json={"body": "Olvidó fichar salida, corregido a mano."},
                headers={"Authorization": f"Bearer {_token_for('administrador')}"},
            )
            assert response.status_code == 201
            body = response.json()
            assert body["entry_id"] == "entry-1"
            assert body["body"] == "Olvidó fichar salida, corregido a mano."
            assert use_case.received_kwargs["author_id"] == "user-1"
    finally:
        app.dependency_overrides.clear()


def test_externo_invitado_cannot_list_time_clock_entry_notes():
    response = None
    try:
        with TestClient(app) as client:
            response = client.get(
                "/time-clock/entries/entry-1/notes",
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_employee_can_list_notes_of_their_own_entry():
    class FakeListNotesUseCase:
        async def execute(self, **kwargs):
            self.received_kwargs = kwargs
            return []

    use_case = FakeListNotesUseCase()
    app.dependency_overrides[time_clock_dependencies.get_list_time_clock_entry_notes_use_case] = (
        lambda: use_case
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/time-clock/entries/entry-1/notes",
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
            assert response.status_code == 200
            assert response.json() == {"notes": []}
            assert use_case.received_kwargs["requester_id"] == "user-1"
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


def test_socio_can_read_current_clock_status_but_not_add_a_note():
    """socio [migración 024] = igual que empleado -> ficha su propio
    horario; sigue sin poder dejar incidencias (exclusivo del admin)."""
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
            headers = {"Authorization": f"Bearer {_token_for('socio')}"}
            status_response = client.get("/time-clock/current", headers=headers)
            note_response = client.post(
                "/time-clock/entries/entry-1/notes", json={"body": "x"}, headers=headers
            )
    finally:
        app.dependency_overrides.clear()

    assert status_response.status_code == 200
    assert note_response.status_code == 403


# --- RF-A3: alta de fichaje en lote (POST /time-clock/entries/batch) ---


def _batch_payload(**overrides) -> dict:
    payload = {
        "date_from": "2026-07-13",
        "date_to": "2026-07-19",
        "clock_in_time": "08:00",
        "clock_out_time": "17:00",
    }
    payload.update(overrides)
    return payload


def test_externo_invitado_cannot_batch_create_time_clock_entries():
    try:
        with TestClient(app) as client:
            response = client.post(
                "/time-clock/entries/batch",
                json=_batch_payload(),
                headers={"Authorization": f"Bearer {_token_for('externo_invitado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_batch_create_returns_200_with_created_and_omitted_breakdown():
    """Nunca 201: el lote puede no crear nada y seguir siendo válido (EC4)."""
    from datetime import UTC, date, datetime

    from src.features.time_clock.application.results import (
        OmittedBatchDay,
        TimeClockEntriesBatchResult,
    )
    from src.features.time_clock.domain.entities import TimeClockEntry

    class FakeBatchUseCase:
        async def execute(self, **kwargs):
            self.received_kwargs = kwargs
            return TimeClockEntriesBatchResult(
                created=[
                    TimeClockEntry(
                        id="entry-1",
                        user_id=kwargs["user_id"],
                        work_date=date(2026, 7, 13),
                        clock_in=datetime(2026, 7, 13, 6, 0, tzinfo=UTC),
                        clock_out=datetime(2026, 7, 13, 15, 0, tzinfo=UTC),
                        source="manual",
                        created_at=datetime(2026, 7, 13, 6, 0, tzinfo=UTC),
                        updated_at=datetime(2026, 7, 13, 6, 0, tzinfo=UTC),
                    )
                ],
                omitted=[
                    OmittedBatchDay(work_date=date(2026, 7, 19), reason="fin_de_semana")
                ],
            )

    use_case = FakeBatchUseCase()
    app.dependency_overrides[
        time_clock_dependencies.get_create_time_clock_entries_batch_use_case
    ] = lambda: use_case
    try:
        with TestClient(app) as client:
            response = client.post(
                "/time-clock/entries/batch",
                json=_batch_payload(),
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert len(body["created"]) == 1
    assert body["created"][0]["source"] == "manual"
    assert body["omitted"] == [{"work_date": "2026-07-19", "reason": "fin_de_semana"}]


def test_batch_create_always_scopes_to_the_current_user_and_their_entity():
    """Nadie ficha por otro: siempre `current_user["sub"]`, igual que
    `POST /entries` — el payload no acepta `user_id`."""
    from src.features.time_clock.application.results import TimeClockEntriesBatchResult

    class FakeBatchUseCase:
        async def execute(self, **kwargs):
            self.received_kwargs = kwargs
            return TimeClockEntriesBatchResult(created=[], omitted=[])

    use_case = FakeBatchUseCase()
    app.dependency_overrides[
        time_clock_dependencies.get_create_time_clock_entries_batch_use_case
    ] = lambda: use_case
    try:
        with TestClient(app) as client:
            jwt_service = get_jwt_service()
            token = jwt_service.create_access_token(
                {
                    "sub": "user-1",
                    "email": "user@ameliahub.com",
                    "role": "empleado",
                    "entity_id": "entity-hub",
                    "is_external": False,
                }
            )
            response = client.post(
                "/time-clock/entries/batch",
                json=_batch_payload(),
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert use_case.received_kwargs["user_id"] == "user-1"
    assert use_case.received_kwargs["entity_id"] == "entity-hub"
    assert use_case.received_kwargs["date_from"].isoformat() == "2026-07-13"
    assert use_case.received_kwargs["date_to"].isoformat() == "2026-07-19"
    assert use_case.received_kwargs["clock_in_time"].isoformat() == "08:00:00"
    assert use_case.received_kwargs["clock_out_time"].isoformat() == "17:00:00"


def test_batch_create_allows_omitting_clock_out_time():
    from src.features.time_clock.application.results import TimeClockEntriesBatchResult

    class FakeBatchUseCase:
        async def execute(self, **kwargs):
            self.received_kwargs = kwargs
            return TimeClockEntriesBatchResult(created=[], omitted=[])

    use_case = FakeBatchUseCase()
    app.dependency_overrides[
        time_clock_dependencies.get_create_time_clock_entries_batch_use_case
    ] = lambda: use_case
    try:
        with TestClient(app) as client:
            response = client.post(
                "/time-clock/entries/batch",
                json={
                    "date_from": "2026-07-13",
                    "date_to": "2026-07-13",
                    "clock_in_time": "08:00",
                },
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert use_case.received_kwargs["clock_out_time"] is None


def test_batch_create_rejects_future_workday_with_422_uniform_body():
    """422 (no 400 — este backend nunca mapea a 400, ver
    `shared/errors/handler.py`), con el mismo cuerpo uniforme
    `{"detail": {"code", "message"}}` que el resto del backend."""
    from src.features.time_clock.domain.errors import TimeClockBatchFutureDateError

    class FakeBatchUseCase:
        async def execute(self, **kwargs):
            raise TimeClockBatchFutureDateError(
                "El lote incluye un día futuro sin ninguna exclusión de "
                "calendario que lo cubra."
            )

    app.dependency_overrides[
        time_clock_dependencies.get_create_time_clock_entries_batch_use_case
    ] = lambda: FakeBatchUseCase()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/time-clock/entries/batch",
                json=_batch_payload(),
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    body = response.json()
    assert body["detail"]["code"] == "TimeClockBatchFutureDateError"
    assert "futuro" in body["detail"]["message"]


def test_batch_create_rejects_range_over_seven_days_with_422():
    from src.features.time_clock.domain.errors import TimeClockBatchRangeTooLongError

    class FakeBatchUseCase:
        async def execute(self, **kwargs):
            raise TimeClockBatchRangeTooLongError(
                "El lote no puede abarcar más de 7 días."
            )

    app.dependency_overrides[
        time_clock_dependencies.get_create_time_clock_entries_batch_use_case
    ] = lambda: FakeBatchUseCase()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/time-clock/entries/batch",
                json=_batch_payload(date_to="2026-07-21"),
                headers={"Authorization": f"Bearer {_token_for('empleado')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "TimeClockBatchRangeTooLongError"
