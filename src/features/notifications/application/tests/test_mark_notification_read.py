import pytest

from src.features.notifications.application.use_cases.mark_notification_read import (
    MarkNotificationReadUseCase,
)
from src.features.notifications.domain.errors import NotificationNotFoundError

from .fakes import FakeNotificationRepository


@pytest.mark.asyncio
async def test_mark_notification_read_marks_own_notification():
    repository = FakeNotificationRepository()
    notification = await repository.create(
        user_id="user-1", type="birthday", title="A", body=None, data={}
    )
    use_case = MarkNotificationReadUseCase(repository)

    updated = await use_case.execute(notification_id=notification.id, user_id="user-1")

    assert updated.read is True


@pytest.mark.asyncio
async def test_mark_notification_read_rejects_someone_elses_notification_as_not_found():
    repository = FakeNotificationRepository()
    notification = await repository.create(
        user_id="user-1", type="birthday", title="A", body=None, data={}
    )
    use_case = MarkNotificationReadUseCase(repository)

    # RGPD: intentar marcar la notificación de OTRO usuario da el mismo 404
    # que un id inexistente — no se filtra la diferencia (ver domain/errors.py).
    with pytest.raises(NotificationNotFoundError):
        await use_case.execute(notification_id=notification.id, user_id="user-2")


@pytest.mark.asyncio
async def test_mark_notification_read_rejects_unknown_id():
    repository = FakeNotificationRepository()
    use_case = MarkNotificationReadUseCase(repository)

    with pytest.raises(NotificationNotFoundError):
        await use_case.execute(notification_id="does-not-exist", user_id="user-1")
