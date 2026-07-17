"""
Tests del adaptador SendGrid. El contenido (`render_email`) se ejercita como
función pura; el I/O HTTP se prueba con `httpx.MockTransport` y un pool en
memoria — nunca se toca la red ni una DB real (mismo criterio que
`test_nager_provider`, donde el HTTP es una capa fina encima de la lógica).
"""

import httpx
import pytest

from src.shared.email.infrastructure.sendgrid_email_sender import (
    SendGridEmailSender,
    render_email,
)


class _FakePool:
    """Registra las llamadas a `execute` para poder afirmar sobre `email_log`
    sin una base de datos."""

    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    async def execute(self, query: str, *args) -> str:
        self.calls.append((query, args))
        return "INSERT 0 1"


def _sender(handler, pool=None) -> SendGridEmailSender:
    return SendGridEmailSender(
        api_key="SG.test",
        from_email="info@amelia.am",
        db_pool=pool or _FakePool(),
        frontend_url="http://localhost:5173",
        transport=httpx.MockTransport(handler),
    )


# --- render_email (función pura, sin red) ---


def test_render_staff_invited_usa_nombre_y_enlace_de_login():
    subject, html = render_email(
        "staff_invited",
        {"full_name": "Ana Gómez", "frontend_url": "https://intranet.amelia.am"},
        frontend_url="http://fallback",
    )
    assert subject == "Te damos la bienvenida a la intranet de Amelia"
    assert "Ana Gómez" in html
    assert "https://intranet.amelia.am" in html


def test_render_staff_invited_cae_a_la_url_por_defecto_sin_contexto():
    _, html = render_email("staff_invited", {"full_name": "Ana"}, frontend_url="http://fallback")
    assert "http://fallback" in html


def test_render_generico_usa_title_y_body_de_la_notificacion():
    subject, html = render_email(
        "absence_approved",
        {"title": "Ausencia aprobada", "body": "Tu solicitud ha sido aprobada."},
        frontend_url="http://localhost:5173",
    )
    assert subject == "Ausencia aprobada"
    assert "Tu solicitud ha sido aprobada." in html


def test_render_escapa_html_del_cuerpo():
    _, html = render_email(
        "announcement_published",
        {"title": "Aviso", "body": "<script>alert(1)</script>"},
        frontend_url="http://x",
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# --- send() (I/O con transporte simulado) ---


async def test_send_ok_registra_sent_con_message_id():
    pool = _FakePool()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer SG.test"
        assert b"info@amelia.am" in request.content
        return httpx.Response(202, headers={"X-Message-Id": "msg-123"})

    result = await _sender(handler, pool).send(
        to="ana@amelia.am", template="staff_invited", context={"full_name": "Ana"}, user_id="u1"
    )

    assert result.status == "sent"
    assert result.provider_message_id == "msg-123"
    assert len(pool.calls) == 1
    args = pool.calls[0][1]
    assert "u1" in args and "ana@amelia.am" in args and "sent" in args


async def test_send_error_registra_failed_y_no_lanza():
    pool = _FakePool()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    result = await _sender(handler, pool).send(
        to="ana@amelia.am", template="staff_invited", context={"full_name": "Ana"}
    )

    assert result.status == "failed"
    assert result.provider_message_id is None
    assert "401" in (result.error_detail or "")
    assert len(pool.calls) == 1
    assert "failed" in pool.calls[0][1]


def test_construir_sin_api_key_falla_al_arrancar():
    with pytest.raises(ValueError):
        SendGridEmailSender(
            api_key="", from_email="x@y.z", db_pool=_FakePool(), frontend_url="http://x"
        )
