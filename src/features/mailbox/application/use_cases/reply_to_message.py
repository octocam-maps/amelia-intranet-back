"""Caso de uso: el admin responde a un mensaje del buzón. La respuesta
queda en el propio registro — el emisor la ve por su `reference_code`
(`TrackMailboxMessageUseCase`), nunca se vincula a un user_id."""

from ...domain.entities import AnonymousMessage
from ...domain.errors import MailboxMessageNotFoundError
from ...domain.ports import IMailboxRepository


class ReplyToMailboxMessageUseCase:
    def __init__(self, repository: IMailboxRepository):
        self._repository = repository

    async def execute(self, *, message_id: str, admin_reply: str) -> AnonymousMessage:
        updated = await self._repository.save_reply(message_id, admin_reply=admin_reply)
        if updated is None:
            raise MailboxMessageNotFoundError("El mensaje del buzón no existe.")
        return updated
