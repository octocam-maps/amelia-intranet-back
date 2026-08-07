"""
Route-level del parte diario del técnico (requerimiento v1.2 §M1).

Lo que se protege aquí es el GUARD, que es donde un rol nuevo hace daño en
silencio: el técnico no debe poder fichar por tramos, el empleado no debe
poder cumplimentar partes, y el administrador debe poder consultarlos y
corregirlos sin poder crear el parte de otro.

Mismo patrón que `test_time_clock_routes.py`: el `JWTService` es el real y
solo se sustituye el caso de uso vía `app.dependency_overrides`.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5999/nonexistent")

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from src.features.time_clock.application.results import TechnicianMonthSummary  # noqa: E402
from src.features.time_clock.infrastructure import dependencies as tc_deps  # noqa: E402
from src.shared.jwt import get_jwt_service  # noqa: E402


def _token_for(role: str, sub: str = "user-1") -> str:
    return get_jwt_service().create_access_token(
        {
            "sub": sub,
            "email": "user@ameliahub.com",
            "role": role,
            "entity_id": None,
            "is_external": role == "externo_invitado",
        }
    )


def _headers(role: str, sub: str = "user-1") -> dict:
    return {"Authorization": f"Bearer {_token_for(role, sub)}"}


class _FakeListUseCase:
    def __init__(self):
        self.received = None

    async def execute(self, **kwargs):
        self.received = kwargs
        return [], TechnicianMonthSummary(
            year=kwargs["year"],
            month=kwargs["month"],
            budget_minutes=9720,
            worked_minutes=0,
            overtime_minutes=0,
            compensation_minutes=0,
            overnight_stays_spain=0,
            overnight_stays_abroad=0,
            is_closed=True,
        )


def _get(path: str, role: str, **kwargs):
    try:
        with TestClient(app) as client:
            return client.get(path, headers=_headers(role), **kwargs)
    finally:
        app.dependency_overrides.clear()


# --- Guards: quién entra y quién no ---------------------------------------


def test_the_technician_cannot_use_the_tramo_based_time_clock():
    """El técnico cumplimenta un parte; el fichaje por tramos no es suyo.
    `TIME_CLOCK_ROLES` no lo incluye y la ruta debe decirlo, no solo el
    navbar."""
    assert _get("/time-clock/entries", "tecnico").status_code == 403


def test_the_technician_cannot_clock_in_live():
    try:
        with TestClient(app) as client:
            response = client.post("/time-clock/clock-in", headers=_headers("tecnico"))
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 403


def test_an_employee_cannot_read_technician_logs():
    """El parte no es un módulo más del control horario: es de otro régimen."""
    assert (
        _get("/time-clock/technician-logs?year=2026&month=8", "empleado").status_code == 403
    )


def test_a_becario_cannot_read_technician_logs():
    assert _get("/time-clock/technician-logs?year=2026&month=8", "becario").status_code == 403


def test_an_externo_cannot_read_technician_logs():
    assert (
        _get("/time-clock/technician-logs?year=2026&month=8", "externo_invitado").status_code
        == 403
    )


def test_the_technician_reads_their_own_month():
    use_case = _FakeListUseCase()
    app.dependency_overrides[tc_deps.get_list_technician_daily_logs_use_case] = lambda: use_case

    response = _get("/time-clock/technician-logs?year=2026&month=8", "tecnico")

    assert response.status_code == 200
    assert response.json()["summary"]["budget_minutes"] == 9720
    assert use_case.received["requester_role"] == "tecnico"


def test_the_admin_reads_another_technicians_month():
    use_case = _FakeListUseCase()
    app.dependency_overrides[tc_deps.get_list_technician_daily_logs_use_case] = lambda: use_case

    response = _get(
        "/time-clock/technician-logs?year=2026&month=8&user_id=otro", "administrador"
    )

    assert response.status_code == 200
    # El guard RGPD vive en el caso de uso, así que lo que la ruta debe
    # garantizar es que le PASA el rol y el id pedido sin recortarlos.
    assert use_case.received["user_id"] == "otro"
    assert use_case.received["requester_role"] == "administrador"


def test_the_admin_cannot_create_a_log_for_someone_else():
    """El parte lo declara quien hizo la jornada. El admin corrige y consulta,
    pero `POST` es solo del técnico — si no, RRHH podría inventar jornadas a
    nombre de otro y el registro dejaría de ser una declaración suya."""
    try:
        with TestClient(app) as client:
            response = client.post(
                "/time-clock/technician-logs",
                headers=_headers("administrador"),
                json={
                    "work_date": "2026-08-05",
                    "started_at": "2026-08-05T08:00:00+02:00",
                    "ended_at": "2026-08-05T20:30:00+02:00",
                    "project_id": "p-1",
                    "work_location": "Guadix",
                    "had_break": False,
                    "break_minutes": 0,
                    "overnight_stay": "ninguna",
                    "product_category": "software",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


# --- Contrato de entrada ---------------------------------------------------


def test_the_payload_rejects_an_unknown_overnight_place():
    """`overnight_stay` es un enum cerrado: un valor libre acabaría en la
    columna y rompería el recuento de pernoctas del Excel."""
    try:
        with TestClient(app) as client:
            response = client.post(
                "/time-clock/technician-logs",
                headers=_headers("tecnico"),
                json={
                    "work_date": "2026-08-05",
                    "started_at": "2026-08-05T08:00:00+02:00",
                    "ended_at": "2026-08-05T20:30:00+02:00",
                    "project_id": "p-1",
                    "work_location": "Guadix",
                    "had_break": False,
                    "break_minutes": 0,
                    "overnight_stay": "portugal",
                    "product_category": "software",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_the_payload_requires_an_explicit_timezone_offset():
    """TZ-1: sin offset, "01:30" es irresoluble entre el día que empieza y el
    siguiente — que es justo el caso que este parte tiene que soportar.

    El caso de uso se sustituye aunque no llegue a ejecutarse: FastAPI resuelve
    las dependencias antes de rechazar el body, y la real abriría el pool de
    Postgres. Sin el override, el fallo sería "no hay base de datos" y este
    test no probaría nada de lo que dice probar.

    Este test destapó además un fallo del manejador global de validación
    (`shared/errors/handler.py`): `exc.errors()` incluye el objeto `ValueError`
    del validador y `json.dumps` no sabe serializarlo, así que el cliente
    recibía un 500 en vez de este 422. Estaba en producción para TODOS los
    endpoints con validador propio.
    """

    class _Unused:
        async def execute(self, **kwargs):  # pragma: no cover - no debe llegar
            raise AssertionError("La validación debe rechazar antes de llegar al caso de uso.")

    app.dependency_overrides[tc_deps.get_create_technician_daily_log_use_case] = _Unused
    try:
        with TestClient(app) as client:
            response = client.post(
                "/time-clock/technician-logs",
                headers=_headers("tecnico"),
                json={
                    "work_date": "2026-08-05",
                    "started_at": "2026-08-05T08:00:00",
                    "ended_at": "2026-08-05T20:30:00",
                    "project_id": "p-1",
                    "work_location": "Guadix",
                    "had_break": False,
                    "break_minutes": 0,
                    "overnight_stay": "ninguna",
                    "product_category": "software",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_worked_minutes_sent_by_the_client_is_ignored_not_trusted():
    """El campo ni siquiera existe en el DTO. Es el dato del que cuelga toda la
    bolsa de 162 h: aceptarlo permitiría declarar 4 horas en una jornada de 12."""
    from src.features.time_clock.infrastructure.schemas import TechnicianDailyLogInputDTO

    assert "worked_minutes" not in TechnicianDailyLogInputDTO.model_fields
