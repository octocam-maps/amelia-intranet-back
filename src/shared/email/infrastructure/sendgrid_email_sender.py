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
_BRAND_BG = "#F9FAFB"


def _shell(subject: str, body_html: str, cta_url: str, cta_label: str) -> str:
    """Envoltorio HTML de marca (navy/verde Amelia) común a todos los correos."""
    return (
        f'<div style="background:{_BRAND_BG};padding:32px 0;font-family:Arial,Helvetica,sans-serif;">'
        f'<div style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;'
        f'border:1px solid #E5E7EB;">'
        f'<div style="background:{_BRAND_NAVY};padding:20px 28px;">'
        f'<span style="color:#ffffff;font-size:18px;font-weight:700;">Amelia</span></div>'
        f'<div style="padding:28px;color:{_BRAND_NAVY};font-size:15px;line-height:1.6;">'
        f"<h1 style=\"font-size:20px;margin:0 0 16px;\">{_html.escape(subject)}</h1>"
        f"{body_html}"
        f'<p style="margin:28px 0 0;">'
        f'<a href="{_html.escape(cta_url)}" '
        f'style="display:inline-block;background:{_BRAND_GREEN};color:{_BRAND_NAVY};'
        f'text-decoration:none;font-weight:700;padding:12px 22px;border-radius:8px;">'
        f"{_html.escape(cta_label)}</a></p>"
        f"</div>"
        f'<div style="padding:16px 28px;color:#6B7280;font-size:12px;border-top:1px solid #E5E7EB;">'
        f"Este es un correo automático de la intranet de Amelia. No respondas a este mensaje.</div>"
        f"</div></div>"
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
            f"<p>{saludo}</p>"
            "<p>RRHH te ha dado de alta en la intranet de Amelia. Accede con tu "
            "cuenta de Google corporativa para completar tu onboarding y empezar "
            "a gestionar tu jornada, ausencias y documentos.</p>"
        )
        return subject, _shell(subject, body_html, login_url, "Entrar a la intranet")

    subject = str(context.get("title") or "Notificación de Amelia")
    raw_body = str(context.get("body") or "").strip()
    body_html = f"<p>{_html.escape(raw_body)}</p>" if raw_body else ""
    return subject, _shell(subject, body_html, frontend_url, "Abrir la intranet")


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
