"""
Adaptador REAL de `IEmailSender` contra la API v3 de SendGrid
(`POST https://api.sendgrid.com/v3/mail/send`). Se activa con
`EMAIL_PROVIDER=sendgrid` (ver `factory.get_email_sender`); el default sigue
siendo `mock`.

Mismo criterio de trazabilidad que `MockEmailSender`: registra cada intento en
`email_log` (`status='sent'` con `sent_at` y `provider_message_id`, o
`status='failed'` con `error_detail`). El envío NO lanza excepción hacia el
caso de uso — devuelve `EmailResult(status='failed')` y deja rastro — porque
todos los disparadores tratan el email como best-effort (un fallo de correo no
revierte el alta ni la notificación in-app; ver `CreateStaffMemberUseCase` y
`NotifyUseCase`).

El contenido se arma con `render_email` (función pura, sin red ni SQL) para
poder testear asunto/HTML con contexto estático, igual que `map_nager_payload`
en el proveedor de festivos.
"""

import html as _html
from typing import Any, Optional

import httpx

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool
from src.shared.logger import get_logger

from ..domain.entities import EmailResult

logger = get_logger("shared.email.sendgrid")

_BRAND_GREEN = "#00D170"
_BRAND_NAVY = "#0F1729"
_BRAND_BG = "#F1F5F9"
_TEXT = "#0F1729"
_MUTED = "#6B7280"
_BORDER = "#E5E7EB"
# Pila de fuentes de sistema: se ve nativa en cada cliente y evita el look
# "Arial genérico". Los clientes que no la soporten caen a Arial igual.
_FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

# El logo se sirve como asset ESTÁTICO del frontend (`public/brand/`, sin hash
# de bundler → ruta estable a prueba de deploys), en el MISMO dominio que la
# intranet. Se referencia por URL absoluta (los emails no resuelven rutas
# relativas) derivada de `frontend_url`, así dev usa localhost y prod usa
# `people.amelia.am` sin tocar el template.
_LOGO_PATH = "/brand/logo-amelia-blanco.png"


def _logo_url(frontend_url: str) -> str:
    return f"{frontend_url.rstrip('/')}{_LOGO_PATH}"


def _cta_url(frontend_url: str, path: str) -> str:
    """Construye el destino del botón a partir del deep-link (`data["url"]`,
    p. ej. `/ausencias`) que ya trae cada notificación, para que el correo
    lleve a la PANTALLA concreta y no a la home. Guarda anti open-redirect:
    solo acepta rutas relativas propias (`/...`); descarta URLs absolutas y
    protocol-relative (`//host`) cayendo a la raíz del frontend."""
    p = (path or "").strip()
    if p.startswith("/") and not p.startswith("//"):
        return f"{frontend_url.rstrip('/')}{p}"
    return frontend_url


def _button(cta_url: str, cta_label: str) -> str:
    """Botón "bulletproof" basado en tabla — se ve consistente en Outlook
    (motor Word), Gmail y Apple Mail, donde un `<a>` con padding falla."""
    return (
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0" '
        'style="margin:28px 0 4px;"><tr>'
        f'<td align="center" bgcolor="{_BRAND_GREEN}" style="border-radius:8px;">'
        f'<a href="{_html.escape(cta_url)}" target="_blank" '
        f'style="display:inline-block;padding:13px 26px;font-family:{_FONT};font-size:15px;'
        f'font-weight:700;color:{_BRAND_NAVY};text-decoration:none;border-radius:8px;">'
        f'{_html.escape(cta_label)}</a></td></tr></table>'
    )


def _shell(
    subject: str,
    body_html: str,
    cta_url: str,
    cta_label: str,
    *,
    logo_url: str,
    preheader: str = "",
) -> str:
    """Documento HTML de marca (navy/verde Amelia) común a todos los correos.

    Documento COMPLETO (no un fragmento): `<!DOCTYPE>` + `<meta charset>` para
    que las tildes se rendericen bien en cualquier cliente y en la vista previa
    del navegador, y layout basado en TABLAS con estilos inline (lo único que
    Outlook renderiza de forma fiable). `preheader` es el texto de vista previa
    que la bandeja muestra junto al asunto — oculto en el cuerpo."""
    pre = _html.escape((preheader or subject).strip())
    return (
        "<!DOCTYPE html>"
        '<html lang="es" xmlns="http://www.w3.org/1999/xhtml">'
        "<head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="X-UA-Compatible" content="IE=edge">'
        '<meta name="x-apple-disable-message-reformatting">'
        f"<title>{_html.escape(subject)}</title>"
        "</head>"
        f'<body style="margin:0;padding:0;background:{_BRAND_BG};">'
        # Preheader oculto: controla el texto de preview en la bandeja de entrada.
        f'<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;'
        f'opacity:0;color:transparent;">{pre}</div>'
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        f'border="0" style="background:{_BRAND_BG};"><tr>'
        '<td align="center" style="padding:32px 16px;">'
        f'<table role="presentation" width="560" cellspacing="0" cellpadding="0" '
        f'border="0" style="max-width:560px;width:100%;background:#ffffff;'
        f'border-radius:14px;overflow:hidden;border:1px solid {_BORDER};">'
        # Cabecera navy con el logo de marca (wordmark blanco). `alt="Amelia"`
        # cubre el caso de imágenes bloqueadas (Gmail/Outlook por defecto): el
        # `color` blanco tiñe ese texto alternativo para que lea sobre el navy.
        f'<tr><td style="background:{_BRAND_NAVY};padding:22px 32px;">'
        f'<img src="{_html.escape(logo_url)}" alt="Amelia" width="148" height="25" '
        'style="display:block;border:0;height:25px;width:148px;'
        'color:#ffffff;font-family:' + _FONT + ';font-size:18px;font-weight:700;">'
        "</td></tr>"
        # Cuerpo.
        f'<tr><td style="padding:32px;font-family:{_FONT};color:{_TEXT};'
        'font-size:15px;line-height:1.6;">'
        f'<h1 style="margin:0 0 16px;font-size:21px;line-height:1.3;'
        f'font-weight:700;color:{_TEXT};">{_html.escape(subject)}</h1>'
        f"{body_html}"
        f"{_button(cta_url, cta_label)}"
        "</td></tr>"
        # Pie dentro de la tarjeta.
        f'<tr><td style="padding:20px 32px;border-top:1px solid {_BORDER};'
        f'font-family:{_FONT};color:{_MUTED};font-size:12px;line-height:1.5;">'
        "Este es un correo automático de la intranet de Amelia. "
        "Por favor, no respondas a este mensaje.</td></tr>"
        "</table>"
        # Sub-pie fuera de la tarjeta.
        f'<table role="presentation" width="560" cellspacing="0" cellpadding="0" '
        'border="0" style="max-width:560px;width:100%;"><tr>'
        f'<td style="padding:16px 8px;text-align:center;font-family:{_FONT};'
        f'color:{_MUTED};font-size:11px;">&copy; Amelia &middot; Intranet corporativa</td>'
        "</tr></table>"
        "</td></tr></table>"
        "</body></html>"
    )


def render_email(
    template: str, context: dict[str, Any], *, frontend_url: str
) -> tuple[str, str]:
    """Función PURA: `(template, context) -> (asunto, html)`. Sin red ni SQL.

    Dos familias de plantilla:
    - `staff_invited` (alta/reenvío de plantilla): trae `full_name` +
      `frontend_url` en el contexto, no `title`/`body`.
    - resto: todo lo que pasa por `NotifyUseCase` trae `title`/`body` (el
      `template` coincide 1:1 con el `type` de la notificación in-app).
    """
    if template == "staff_invited":
        full_name = str(context.get("full_name") or "").strip()
        login_url = str(context.get("frontend_url") or frontend_url)
        subject = "Te damos la bienvenida a la intranet de Amelia"
        saludo = f"Hola {_html.escape(full_name)}," if full_name else "Hola,"
        body_html = (
            f'<p style="margin:0 0 14px;">{saludo}</p>'
            '<p style="margin:0 0 14px;">RRHH te ha dado de alta en la intranet de '
            "Amelia. Accede con tu cuenta de Google corporativa para completar tu "
            "onboarding y empezar a gestionar tu jornada, ausencias y documentos.</p>"
        )
        return subject, _shell(
            subject,
            body_html,
            login_url,
            "Entrar a la intranet",
            logo_url=_logo_url(login_url),
            preheader="Completa tu onboarding y empieza a gestionar tu día a día en Amelia.",
        )

    subject = str(context.get("title") or "Notificación de Amelia")
    raw_body = str(context.get("body") or "").strip()
    body_html = (
        f'<p style="margin:0;">{_html.escape(raw_body)}</p>' if raw_body else ""
    )
    # El botón lleva al deep-link de la notificación (`/ausencias`,
    # `/control-horario`, …) si viene; si no, a la raíz del frontend.
    cta_url = _cta_url(frontend_url, str(context.get("url") or ""))
    return subject, _shell(
        subject,
        body_html,
        cta_url,
        "Ver en la intranet",
        logo_url=_logo_url(frontend_url),
        preheader=raw_body or subject,
    )


def _describe_error(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}: {exc.response.text[:400]}"
    return str(exc)[:400]


class SendGridEmailSender:
    _API_URL = "https://api.sendgrid.com/v3/mail/send"
    _TIMEOUT_SECONDS = 10.0

    def __init__(
        self,
        api_key: str,
        from_email: str,
        db_pool: DatabasePool,
        frontend_url: str,
        *,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        # Falla al construir (no al enviar) si falta la key — así el error salta
        # al arrancar la app con `EMAIL_PROVIDER=sendgrid` mal configurado, no
        # en silencio al primer correo.
        if not api_key:
            raise ValueError(
                "SENDGRID_API_KEY está vacío: no se puede usar EMAIL_PROVIDER=sendgrid."
            )
        self._api_key = api_key
        self._from_email = from_email
        self._db = db_pool
        self._frontend_url = frontend_url
        self._transport = transport  # inyectable solo en tests (httpx.MockTransport)

    async def send(
        self,
        *,
        to: str,
        template: str,
        context: dict[str, Any],
        user_id: Optional[str] = None,
    ) -> EmailResult:
        subject, body_html = render_email(template, context, frontend_url=self._frontend_url)
        payload = {
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": self._from_email},
            "subject": subject,
            "content": [{"type": "text/html", "value": body_html}],
        }

        try:
            async with httpx.AsyncClient(
                timeout=self._TIMEOUT_SECONDS, transport=self._transport
            ) as client:
                response = await client.post(
                    self._API_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            error_detail = _describe_error(exc)
            await self._log(user_id, to, template, "failed", None, error_detail)
            logger.error(
                "SendGrid email failed", to=to, template=template, error=error_detail
            )
            return EmailResult(status="failed", provider_message_id=None, error_detail=error_detail)

        # SendGrid devuelve 202 sin cuerpo; el id del mensaje viaja en la cabecera.
        message_id = response.headers.get("X-Message-Id")
        await self._log(user_id, to, template, "sent", message_id, None)
        logger.info(
            "SendGrid email sent", to=to, template=template, provider_message_id=message_id
        )
        return EmailResult(status="sent", provider_message_id=message_id)

    async def _log(
        self,
        user_id: Optional[str],
        to: str,
        template: str,
        status: str,
        provider_message_id: Optional[str],
        error_detail: Optional[str],
    ) -> None:
        # `sent_at` solo se sella cuando el correo realmente salió.
        await self._db.execute(
            """
            INSERT INTO email_log
                (user_id, to_email, template, status, provider_message_id, error_detail, sent_at)
            VALUES ($1, $2, $3, $4, $5, $6,
                    CASE WHEN $4 = 'sent' THEN CURRENT_TIMESTAMP ELSE NULL END)
            """,
            user_id,
            to,
            template,
            status,
            provider_message_id,
            error_detail,
        )
