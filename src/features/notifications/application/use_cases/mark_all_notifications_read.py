from ...domain.ports import INotificationRepository


class MarkAllNotificationsReadUseCase:
    def __init__(self, repository: INotificationRepository):
        self._repository = repository

    async def execute(self, *, user_id: str) -> int:
        return await self._repository.mark_all_read(user_id)
