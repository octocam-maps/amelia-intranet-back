"""
Caso de uso reutilizable: crea la(s) notificación(es) in-app y dispara el
email correspondiente EN UN SOLO FLUJO. Cada disparador (absences,
announcements, mailbox, jobs por-tiempo) hace UNA sola llamada a
`execute()` — incluso cuando hace fan-out a varios destinatarios (p. ej. un
anuncio publicado a toda la plantilla activa).
"""

from typing import Any, Optional

from src.shared.email.domain.ports import IEmailSender
from src.shared.logger import get_logger

from ...domain.entities import Notification
from ...domain.ports import INotificationRepository

logger = get_logger("notifications.notify")


class NotifyUseCase:
    def __init__(self, repository: INotificationRepository, email_sender: IEmailSender):
        self._repository = repository
        self._email_sender = email_sender

    async def execute(
        self,
        *,
        recipient_ids: list[str],
        type: str,
        title: str,
        body: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
        send_email: bool = True,
    ) -> list[Notification]:
        """Una fila de `notifications` por destinatario + un envío de email
        por destinatario. El email es best-effort: un fallo al enviarlo NO
        revierte la notificación in-app, que es la garantía mínima que ya
        tiene el usuario en cuanto entra a la intranet."""
        payload = data or {}
        notifications: list[Notification] = []
        for user_id in recipient_ids:
            notification = await self._repository.create(
                user_id=user_id, type=type, title=title, body=body, data=payload
            )
            notifications.append(notification)

            if not send_email:
                continue
            email = await self._repository.find_email(user_id)
            if email is None:
                continue
            try:
                await self._email_sender.send(
                    to=email,
                    template=type,
                    context={"title": title, "body": body, **payload},
                    user_id=user_id,
                )
            except Exception as e:
                logger.error(
                    "Notification email failed",
                    type=type,
                    user_id=user_id,
                    error=str(e),
                )
        return notifications

    async def notify_admins(
        self,
        *,
        type: str,
        title: str,
        body: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> list[Notification]:
        """Atajo para los disparadores que notifican a la bandeja del admin
        (`absence_requested`, `mailbox_message`) — resuelve destinatarios
        aquí para que el feature dueño del evento no necesite conocer cómo
        se identifica a un administrador."""
        admin_ids = await self._repository.list_admin_ids()
        return await self.execute(recipient_ids=admin_ids, type=type, title=title, body=body, data=data)

    async def notify_team_excluding_role(
        self,
        role_code: str,
        *,
        type: str,
        title: str,
        body: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
        exclude_user_ids: Optional[list[str]] = None,
    ) -> list[Notification]:
        """Atajo genérico para el fan-out a toda la plantilla activa salvo
        un rol. `announcements` ya no lo usa para su propio disparador (ver
        `notify_announcement`, que acota por audiencia) — se mantiene por si
        otro disparador necesita este mismo recorte a futuro.

        `exclude_user_ids` recorta ADEMÁS por id concreto — lo usa el
        cumpleaños para que el propio cumpleañero no reciba su notificación
        en tercera persona ("¡Hoy es el cumpleaños de Ana!")."""
        recipient_ids = await self._repository.list_active_user_ids_excluding_role(role_code)
        if exclude_user_ids:
            excluded = set(exclude_user_ids)
            recipient_ids = [uid for uid in recipient_ids if uid not in excluded]
        return await self.execute(
            recipient_ids=recipient_ids, type=type, title=title, body=body, data=data
        )

    async def notify_announcement(
        self,
        *,
        audience: str,
        entity_id: Optional[str],
        role_id: Optional[str],
        type: str,
        title: str,
        body: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> list[Notification]:
        """Atajo para `announcement_published` — resuelve destinatarios
        acotados a la MISMA audiencia que el anuncio (`all`/`entity`/`role`)
        en vez de avisar a toda la plantilla. `externo_invitado` queda
        excluido siempre (ver `list_announcement_recipient_ids`)."""
        recipient_ids = await self._repository.list_announcement_recipient_ids(
            audience=audience, entity_id=entity_id, role_id=role_id
        )
        return await self.execute(
            recipient_ids=recipient_ids, type=type, title=title, body=body, data=data
        )
