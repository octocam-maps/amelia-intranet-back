"""
Puerto (Protocol) del envío de email transaccional. `domain` no importa nada
de `infrastructure` — la implementación concreta (mock hoy, un proveedor real
más adelante) se inyecta por duck typing estructural, igual que el resto de
puertos del proyecto (`src/shared/jwt`, `features/*/domain/ports.py`).
"""

from typing import Any, Optional, Protocol

from .entities import EmailResult


class IEmailSender(Protocol):
    async def send(
        self,
        *,
        to: str,
        template: str,
        context: dict[str, Any],
        user_id: Optional[str] = None,
    ) -> EmailResult:
        """`template` identifica el tipo de email (hoy coincide 1:1 con el
        `type` de la notificación in-app, p. ej. `absence_approved`).
        `user_id` es opcional y solo se usa para trazabilidad en
        `email_log.user_id` (`NULL` si no aplica, p. ej. el buzón anónimo
        nunca lo pasa — ver `NotifyUseCase`)."""
        ...
