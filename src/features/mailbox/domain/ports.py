"""
Puerto (Protocol) del feature `mailbox`. `domain` no importa nada de
`infrastructure` ni de FastAPI — la implementación concreta (asyncpg) vive
en `infrastructure` y se inyecta aquí por duck typing estructural.
"""

from typing import Optional, Protocol

from .entities import AnonymousMessage


class IMailboxRepository(Protocol):
    async def create_message(
        self, *, category: str, subject: Optional[str], body: str
    ) -> AnonymousMessage:
        """Genera el `reference_code` y lo persiste — es una decisión de
        infraestructura (necesita reintentar contra la UNIQUE de la BD ante
        una colisión), el caso de uso no la conoce."""
        ...

    async def find_by_id(self, message_id: str) -> Optional[AnonymousMessage]: ...

    async def find_by_reference_code(self, reference_code: str) -> Optional[AnonymousMessage]:
        """Único canal de seguimiento del emisor anónimo — por diseño no
        hay `find_by_user_id`, esta tabla no sabe quién escribió qué."""
        ...

    async def list_messages(self, *, status_filter: Optional[str]) -> list[AnonymousMessage]:
        """`status_filter`: `"unread"` -> `status='new'`; `"resolved"` ->
        `status='resolved'`; `None`/`"all"` -> sin filtro."""
        ...

    async def save_reply(self, message_id: str, *, admin_reply: str) -> Optional[AnonymousMessage]:
        """Guarda la respuesta del admin. Si el mensaje estaba `new` pasa a
        `read`; si ya estaba `resolved` se deja como estaba (reabrir es
        responsabilidad de un flujo distinto, no de responder)."""
        ...

    async def mark_resolved(self, message_id: str) -> Optional[AnonymousMessage]: ...
