"""Caso de uso: el emisor anónimo consulta su propio mensaje por
`reference_code`. Sin auth por diseño — exigir un token aquí ataría el
seguimiento a una identidad y rompería el anonimato."""

from ...domain.entities import AnonymousMessage
from ...domain.errors import MailboxMessageNotFoundError
from ...domain.ports import IMailboxRepository


class TrackMailboxMessageUseCase:
    def __init__(self, repository: IMailboxRepository):
        self._repository = repository

    async def execute(self, *, reference_code: str) -> AnonymousMessage:
        message = await self._repository.find_by_reference_code(reference_code)
        if message is None:
            raise MailboxMessageNotFoundError(
                "No existe ningún mensaje con ese código de seguimiento."
            )
        return message
