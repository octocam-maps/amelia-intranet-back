"""
Caso de uso: enviar un mensaje anónimo al buzón. Deliberadamente NO recibe
ni un `user_id` ni una IP — el router exige un rol autenticado solo para
frenar spam (docs/fase-0-esquema-datos.md § buzón anónimo), pero a partir de
aquí ninguna capa vuelve a tocar la identidad del emisor.
"""

from typing import Optional

from ...domain.entities import AnonymousMessage
from ...domain.ports import IMailboxRepository


class SubmitAnonymousMessageUseCase:
    def __init__(self, repository: IMailboxRepository):
        self._repository = repository

    async def execute(self, *, category: str, subject: Optional[str], body: str) -> AnonymousMessage:
        return await self._repository.create_message(category=category, subject=subject, body=body)
