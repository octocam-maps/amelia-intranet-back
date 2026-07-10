from ...domain.ports import INotificationRepository


class GetUnreadCountUseCase:
    def __init__(self, repository: INotificationRepository):
        self._repository = repository

    async def execute(self, *, user_id: str) -> int:
        return await self._repository.count_unread(user_id)
