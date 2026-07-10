"""Caso de uso: listar las notificaciones propias, paginadas por cursor
(`created_at`). RGPD: siempre `user_id=requester_id` — nunca se acepta un
`user_id` externo, cada quien lee SOLO las suyas (docs/CLAUDE.md § alcance
de datos)."""

from datetime import datetime
from typing import NamedTuple, Optional

from ...domain.entities import Notification
from ...domain.ports import INotificationRepository


class NotificationPage(NamedTuple):
    items: list[Notification]
    next_before: Optional[datetime]


class ListNotificationsUseCase:
    def __init__(self, repository: INotificationRepository):
        self._repository = repository

    async def execute(
        self, *, user_id: str, limit: int, before: Optional[datetime]
    ) -> NotificationPage:
        # Pide una de más para saber si queda página siguiente sin una
        # segunda query (COUNT aparte) — patrón estándar de paginación cursor.
        rows = await self._repository.list_for_user(user_id, limit=limit + 1, before=before)
        has_more = len(rows) > limit
        items = rows[:limit]
        next_before = items[-1].created_at if has_more and items else None
        return NotificationPage(items=items, next_before=next_before)
