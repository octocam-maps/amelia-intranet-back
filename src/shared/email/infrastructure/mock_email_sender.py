"""
Adaptador MOCK de `IEmailSender` — el único que esta fase instancia de
verdad (ver `factory.get_email_sender`). NUNCA hace una petición de red ni
toca la API key de SendGrid: registra el intento en `email_log` con
`status='sent'` y un `provider_message_id` sintético, y loguea. Es
indistinguible desde `NotifyUseCase` de un envío real — el día que RRHH
habilite un proveedor real, solo cambia qué clase construye la factory.
"""

import uuid
from typing import Any, Optional

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool
from src.shared.logger import get_logger

from ..domain.entities import EmailResult

logger = get_logger("shared.email.mock")


class MockEmailSender:
    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    async def send(
        self,
        *,
        to: str,
        template: str,
        context: dict[str, Any],
        user_id: Optional[str] = None,
    ) -> EmailResult:
        provider_message_id = f"mock-{uuid.uuid4()}"
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
            provider_message_id=provider_message_id,
        )
        return EmailResult(status="sent", provider_message_id=provider_message_id)
