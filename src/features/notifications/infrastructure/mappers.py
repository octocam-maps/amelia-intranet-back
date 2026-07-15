from ..application.use_cases.list_notifications import NotificationPage
from ..domain.entities import Notification
from .schemas import NotificationDTO, NotificationListDTO


def notification_to_dto(notification: Notification) -> NotificationDTO:
    return NotificationDTO(
        id=notification.id,
        type=notification.type,
        title=notification.title,
        body=notification.body,
        data=notification.data,
        read=notification.read,
        created_at=notification.created_at,
    )


def page_to_dto(page: NotificationPage) -> NotificationListDTO:
    return NotificationListDTO(
        items=[notification_to_dto(n) for n in page.items],
        next_before=page.next_before,
    )
