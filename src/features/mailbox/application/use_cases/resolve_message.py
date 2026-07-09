"""Caso de uso: marcar un mensaje del buzón como resuelto."""

from ...domain.entities import AnonymousMessage
from ...domain.errors import MailboxMessageNotFoundError
from ...domain.ports import IMailboxRepository


class ResolveMailboxMessageUseCase:
    def __init__(self, repository: IMailboxRepository):
        self._repository = repository

    async def execute(self, *, message_id: str) -> AnonymousMessage:
        updated = await self._repository.mark_resolved(message_id)
        if updated is None:
            raise MailboxMessageNotFoundError("El mensaje del buzón no existe.")
        return updated
