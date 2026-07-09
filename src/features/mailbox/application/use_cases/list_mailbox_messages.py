"""Caso de uso: bandeja de recepción del buzón (exclusiva del admin,
docs/permisos-roles.md § Buzón anónimo)."""

from typing import Optional

from ...domain.entities import AnonymousMessage
from ...domain.ports import IMailboxRepository


class ListMailboxMessagesUseCase:
    def __init__(self, repository: IMailboxRepository):
        self._repository = repository

    async def execute(self, *, status_filter: Optional[str]) -> list[AnonymousMessage]:
        return await self._repository.list_messages(status_filter=status_filter)
