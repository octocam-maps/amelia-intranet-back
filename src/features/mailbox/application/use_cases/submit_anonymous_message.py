"""
Caso de uso: enviar un mensaje anónimo al buzón. Deliberadamente NO recibe
ni un `user_id` ni una IP — el router exige un rol autenticado solo para
frenar spam (docs/fase-0-esquema-datos.md § buzón anónimo), pero a partir de
aquí ninguna capa vuelve a tocar la identidad del emisor.
"""

from typing import Optional

from src.features.notifications.application.use_cases.notify import NotifyUseCase

from ...domain.entities import AnonymousMessage
from ...domain.ports import IMailboxRepository


class SubmitAnonymousMessageUseCase:
    def __init__(self, repository: IMailboxRepository, notify: Optional[NotifyUseCase] = None):
        self._repository = repository
        self._notify = notify  # opcional — ver ReviewAbsenceRequestUseCase

    async def execute(self, *, category: str, subject: Optional[str], body: str) -> AnonymousMessage:
        message = await self._repository.create_message(category=category, subject=subject, body=body)

        if self._notify is not None:
            # CRÍTICO ANONIMATO: solo texto genérico + categoría. Nunca
            # `subject`/`body` (podrían identificar al remitente por
            # redacción) ni, por supuesto, IP o user_id — el buzón no tiene
            # identidad por diseño (ver docstring de arriba).
            await self._notify.notify_admins(
                type="mailbox_message",
                title="Nuevo mensaje en el buzón anónimo",
                body=f"Categoría: {category}",
                data={"url": "/administracion/buzon"},
            )

        return message
