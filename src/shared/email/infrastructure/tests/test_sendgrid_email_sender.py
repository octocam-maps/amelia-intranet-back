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


# ─────────────────────────────────────────────────────────────────────────────
# Plantillas editables por el admin (migración 041). Lo que se protege aquí es
# que personalizar un correo no pueda romper el correo.
# ─────────────────────────────────────────────────────────────────────────────

from src.shared.email.domain.entities import EmailTemplate  # noqa: E402
from src.shared.email.infrastructure.sendgrid_email_sender import (  # noqa: E402
    render_placeholders,
)

_FRONTEND = "https://intranet.ameliahub.com"


def _template(**overrides) -> EmailTemplate:
    defaults = {
        "template_key": "staff_invited",
        "label": "Bienvenida",
        "description": "x",
        "subject": "Bienvenida, {{full_name}}",
        "body": "Hola {{full_name}}, entras como {{job_title}}.",
        "is_active": True,
    }
    return EmailTemplate(**{**defaults, **overrides})


class TestRenderPlaceholders:
    def test_replaces_whitelisted_fields(self):
        rendered = render_placeholders("Hola {{full_name}}", {"full_name": "Ana"})
        assert rendered == "Hola Ana"

    def test_tolerates_spaces_inside_the_braces(self):
        assert render_placeholders("{{ full_name }}", {"full_name": "Ana"}) == "Ana"

    def test_escapes_values_in_the_body(self):
        """El `body` lo escribe el admin, pero los VALORES vienen de la BD y
        no deben poder inyectar markup en el correo."""
        rendered = render_placeholders(
            "<p>{{full_name}}</p>", {"full_name": "<b>Ana</b>"}
        )

        assert "&lt;b&gt;Ana&lt;/b&gt;" in rendered
        assert "<b>Ana</b>" not in rendered

    def test_does_not_escape_when_asked_not_to(self):
        """El ASUNTO es texto plano, no HTML: escaparlo haría que un apellido con
        `&` llegara como `&amp;` a la bandeja de entrada."""
        assert render_placeholders(
            "{{full_name}}", {"full_name": "Ruiz & Co"}, escape=False
        ) == "Ruiz & Co"

    def test_an_unknown_placeholder_stays_literal(self):
        """Vaciarlo convierte "Hola {{nombe}}," en "Hola ," y nadie sabe por qué.
        Literal, el admin ve su errata en la previsualización."""
        rendered = render_placeholders("Hola {{nombe}}", {"full_name": "Ana"})
        assert rendered == "Hola {{nombe}}"

    def test_a_field_outside_the_whitelist_is_not_substituted(self):
        """La lista blanca evita que el admin filtre a un correo un dato que ese
        envío no debía incluir."""
        rendered = render_placeholders("{{secreto}}", {"secreto": "no-deberia-salir"})

        assert "no-deberia-salir" not in rendered

    def test_a_missing_value_stays_literal_instead_of_emptying(self):
        assert render_placeholders("{{job_title}}", {}) == "{{job_title}}"


class TestRenderEmailWithOverride:
    def test_uses_the_admin_text(self):
        subject, html = render_email(
            "staff_invited",
            {"full_name": "Ana", "job_title": "PM"},
            frontend_url=_FRONTEND,
            override=_template(),
        )

        assert subject == "Bienvenida, Ana"
        assert "entras como PM" in html

    def test_keeps_the_email_frame(self):
        """El admin edita el mensaje, NO el envoltorio: si pudiera editar el HTML
        completo, un guardado mal hecho dejaría a toda la plantilla sin logo."""
        _, html = render_email(
            "staff_invited", {"full_name": "Ana"}, frontend_url=_FRONTEND,
            override=_template(body="solo esto"),
        )

        assert "<html" in html.lower()
        assert _FRONTEND in html

    def test_without_an_override_it_uses_the_default_text(self):
        subject, _ = render_email(
            "staff_invited", {"full_name": "Ana"}, frontend_url=_FRONTEND
        )

        assert subject == "Te damos la bienvenida a la intranet de Amelia"

    def test_an_inactive_override_falls_back_to_the_default_text(self):
        """`is_active=False` = "usa el texto por defecto", que es el botón
        «Restaurar» de la pantalla."""
        subject, _ = render_email(
            "staff_invited",
            {"full_name": "Ana"},
            frontend_url=_FRONTEND,
            override=_template(is_active=False, subject="No debería salir"),
        )

        assert subject == "Te damos la bienvenida a la intranet de Amelia"

    def test_an_override_cannot_break_a_notification_email(self):
        """Las plantillas genéricas se siembran con `{{title}}`/`{{body}}`: el
        contenido lo sigue escribiendo el caso de uso (una ausencia aprobada tiene
        que decir QUÉ ausencia) y el admin cambia el envoltorio."""
        subject, html = render_email(
            "absence_approved",
            {
                "title": "Ausencia aprobada",
                "body": "Del 3 al 7 de agosto",
                "url": "/ausencias",
            },
            frontend_url=_FRONTEND,
            override=_template(
                template_key="absence_approved",
                subject="{{title}}",
                body="{{body}}\n\nUn saludo del equipo.",
            ),
        )

        assert subject == "Ausencia aprobada"
        assert "Del 3 al 7 de agosto" in html
        assert "Un saludo del equipo." in html


# ─────────────────────────────────────────────────────────────────────────────
# Texto plano → HTML (migración 044). El editor ya NO pide HTML: una persona de
# RRHH no tiene por qué saber cerrar un `<p>`, y una etiqueta mal escrita rompía
# el correo de toda la plantilla sin que nadie lo viera hasta las bandejas.
# ─────────────────────────────────────────────────────────────────────────────

from src.shared.email.infrastructure.sendgrid_email_sender import (  # noqa: E402
    plain_text_to_html,
)


class TestPlainTextToHtml:
    def test_a_blank_line_starts_a_new_paragraph(self):
        html = plain_text_to_html("Hola Ana,\n\nTe damos la bienvenida.")

        assert html.count("<p ") == 2
        assert "Hola Ana," in html
        assert "Te damos la bienvenida." in html

    def test_a_single_line_break_is_a_br_inside_the_same_paragraph(self):
        html = plain_text_to_html("Primera línea\nSegunda línea")

        assert html.count("<p ") == 1
        assert "<br>" in html

    def test_tolerates_stray_spaces_between_paragraphs(self):
        """Un copiar-pegar desde Word o desde un correo deja espacios en la línea
        "vacía". Si no se toleran, los dos párrafos salen pegados en uno."""
        html = plain_text_to_html("Uno\n   \nDos")

        assert html.count("<p ") == 2

    def test_double_asterisks_become_bold(self):
        """`**texto**`, igual que WhatsApp: es una convención que ya conoce
        cualquiera, no una etiqueta que haya que aprender."""
        html = plain_text_to_html("Lee el **manual** antes de firmar")

        assert "<strong>manual</strong>" in html

    def test_urls_and_emails_are_linked_automatically(self):
        html = plain_text_to_html(
            "Entra en https://intranet.ameliahub.com o escribe a rrhh@ameliahub.com"
        )

        assert '<a href="https://intranet.ameliahub.com"' in html
        assert '<a href="mailto:rrhh@ameliahub.com"' in html

    def test_the_admin_cannot_inject_markup(self):
        """EL TEST QUE IMPORTA. El texto se escapa ANTES de aplicar negrita y
        enlaces, así que las únicas etiquetas que sobreviven son las que genera
        esta función."""
        html = plain_text_to_html("<script>alert('x')</script>")

        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_normal_text_with_angle_brackets_survives(self):
        """El motivo por el que el editor de HTML era una trampa: escribir
        "temperatura < 5º" convertía el resto del correo en una etiqueta a
        medias."""
        html = plain_text_to_html("Avisa si la temperatura < 5º y el pH > 7")

        assert "&lt; 5º" in html
        assert "&gt; 7" in html

    def test_ampersands_are_not_broken(self):
        html = plain_text_to_html("Departamento de I+D & Calidad")

        assert "I+D &amp; Calidad" in html

    def test_empty_text_produces_no_paragraph(self):
        assert plain_text_to_html("") == ""
        assert plain_text_to_html("   \n  \n ") == ""


class TestRenderEmailWithPlainTextTemplate:
    def test_the_admin_writes_text_and_receives_html(self):
        subject, html = render_email(
            "staff_invited",
            {"full_name": "Ana"},
            frontend_url=_FRONTEND,
            override=_template(
                subject="Bienvenida, {{full_name}}",
                body="Hola {{full_name}},\n\nEntra con tu cuenta de Google.",
            ),
        )

        assert subject == "Bienvenida, Ana"
        assert html.count("<p ") >= 2
        assert "Hola Ana," in html

    def test_a_placeholder_value_with_markup_is_escaped(self):
        """El valor viene de la BD, no del admin: no debe poder inyectar nada
        aunque alguien guarde un nombre con etiquetas."""
        _, html = render_email(
            "staff_invited",
            {"full_name": "<b>Ana</b>"},
            frontend_url=_FRONTEND,
            override=_template(body="Hola {{full_name}}"),
        )

        assert "<b>Ana</b>" not in html
        assert "&lt;b&gt;Ana&lt;/b&gt;" in html
