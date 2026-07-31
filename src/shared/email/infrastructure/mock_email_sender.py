"""
Adaptador MOCK de `IEmailSender` — el único que esta fase instancia de
verdad (ver `factory.get_email_sender`). NUNCA hace una petición de red ni
toca la API key de SendGrid: registra el intento en `email_log` con
`status='sent'` y un `provider_message_id` sintético, y loguea. Es
indistinguible desde `NotifyUseCase` de un envío real — el día que RRHH
habilite un proveedor real, solo cambia qué clase construye la factory.

SÍ RENDERIZA el asunto (migración 041): con SendGrid sin configurar —que es la
situación real en dev y en producción a día de hoy—, este log es la ÚNICA forma
de comprobar que una plantilla editada por el admin produce el texto esperado.
Sin esto, la pantalla de plantillas de email no se podría verificar de ninguna
manera hasta que ops active el proveedor.
"""

import uuid
from typing import Any, Optional

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool
from src.shared.logger import get_logger

from ..domain.entities import EmailResult
from ..domain.ports import IEmailTemplateProvider
from .sendgrid_email_sender import render_email

logger = get_logger("shared.email.mock")


class MockEmailSender:
    def __init__(
        self,
        db_pool: DatabasePool,
        *,
        frontend_url: str = "",
        template_provider: Optional[IEmailTemplateProvider] = None,
    ):
        self._db = db_pool
        self._frontend_url = frontend_url
        self._template_provider = template_provider

    async def send(
        self,
        *,
        to: str,
        template: str,
        context: dict[str, Any],
        user_id: Optional[str] = None,
    ) -> EmailResult:
        provider_message_id = f"mock-{uuid.uuid4()}"
        # Se renderiza para poder VER el resultado en el log (ver docstring). El
        # render no puede tumbar un envío que de todos modos no sale a la red:
        # si falla, se registra el intento igual.
        subject = template
        try:
            override = (
                await self._template_provider.get(template)
                if self._template_provider is not None
                else None
            )
            subject, _ = render_email(
                template, context, frontend_url=self._frontend_url, override=override
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Mock email could not render the template",
                template=template,
                error_type=type(exc).__name__,
            )
        await self._db.execute(
            """
            INSERT INTO email_log (user_id, to_email, template, status, provider_message_id, sent_at)
            VALUES ($1, $2, $3, 'sent', $4, CURRENT_TIMESTAMP)
            """,
            user_id,
            to,
            template,
            provider_message_id,
        )
        logger.info(
            "Mock email sent",
            to=to,
            template=template,
            subject=subject,
            provider_message_id=provider_message_id,
        )
        return EmailResult(status="sent", provider_message_id=provider_message_id)
