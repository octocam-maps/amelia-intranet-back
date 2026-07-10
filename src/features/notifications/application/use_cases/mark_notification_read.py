"""Caso de uso: marcar una notificación propia como leída. RGPD: el
repositorio condiciona el UPDATE a `user_id` en la propia query — si la
notificación existe pero es de otro usuario, `mark_read` devuelve `None`
igual que si no existiera (nunca se filtra la diferencia, ver domain/errors.py)."""

from ...domain.entities import Notification
from ...domain.errors import NotificationNotFoundError
from ...domain.ports import INotificationRepository


class MarkNotificationReadUseCase:
    def __init__(self, repository: INotificationRepository):
        self._repository = repository

    async def execute(self, *, notification_id: str, user_id: str) -> Notification:
        notification = await self._repository.mark_read(notification_id, user_id)
        if notification is None:
            raise NotificationNotFoundError("La notificación no existe.")
        return notification
