"""Fakes en memoria de `INotificationRepository`/`IEmailSender` — permiten
testear los casos de uso sin Postgres, igual que en `features/absences` y
`features/mailbox`."""

import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Optional

from src.features.notifications.domain.entities import Notification
from src.shared.email.domain.entities import EmailResult


class FakeNotificationRepository:
    def __init__(self):
        self.notifications: dict[str, Notification] = {}
        self.emails_by_user: dict[str, str] = {}
        self.admin_ids: list[str] = []
        self.active_user_ids_by_excluded_role: dict[str, list[str]] = {}
        # Clave (audience, entity_id, role_id) -> destinatarios ya
        # acotados — el filtrado real (SQL) se testea contra el pool
        # mockeado en `infrastructure/tests/test_notification_repository.py`;
        # aquí solo importa que `NotifyUseCase` reenvíe los parámetros.
        self.announcement_recipients: dict[tuple[str, Optional[str], Optional[str]], list[str]] = {}
        self.birthday_users: list[tuple[str, str]] = []
        self.anniversary_users: list[tuple[str, int]] = []
        self.user_ids_with_open_entry: list[str] = []

    async def create(
        self, *, user_id: str, type: str, title: str, body: Optional[str], data: dict[str, Any]
    ) -> Notification:
        notification = Notification(
            id=str(uuid.uuid4()),
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            data=data,
            read_at=None,
            created_at=datetime.now(timezone.utc),
        )
        self.notifications[notification.id] = notification
        return notification

    async def list_for_user(
        self, user_id: str, *, limit: int, before: Optional[datetime]
    ) -> list[Notification]:
        items = [n for n in self.notifications.values() if n.user_id == user_id]
        if before is not None:
            items = [n for n in items if n.created_at < before]
        items.sort(key=lambda n: n.created_at, reverse=True)
        return items[:limit]

    async def count_unread(self, user_id: str) -> int:
        return sum(
            1 for n in self.notifications.values() if n.user_id == user_id and not n.read
        )

    async def mark_read(self, notification_id: str, user_id: str) -> Optional[Notification]:
        existing = self.notifications.get(notification_id)
        if existing is None or existing.user_id != user_id:
            return None
        updated = replace(existing, read_at=datetime.now(timezone.utc))
        self.notifications[notification_id] = updated
        return updated

    async def mark_all_read(self, user_id: str) -> int:
        updated_count = 0
        for notification_id, notification in list(self.notifications.items()):
            if notification.user_id == user_id and not notification.read:
                self.notifications[notification_id] = replace(
                    notification, read_at=datetime.now(timezone.utc)
                )
                updated_count += 1
        return updated_count

    async def find_email(self, user_id: str) -> Optional[str]:
        return self.emails_by_user.get(user_id)

    async def list_admin_ids(self) -> list[str]:
        return list(self.admin_ids)

    async def list_active_user_ids_excluding_role(self, role_code: str) -> list[str]:
        return list(self.active_user_ids_by_excluded_role.get(role_code, []))

    async def list_announcement_recipient_ids(
        self, *, audience: str, entity_id: Optional[str], role_id: Optional[str]
    ) -> list[str]:
        return list(self.announcement_recipients.get((audience, entity_id, role_id), []))

    async def list_birthday_user_ids(self, *, month: int, day: int) -> list[tuple[str, str]]:
        return list(self.birthday_users)

    async def list_anniversary_users(self, *, month: int, day: int) -> list[tuple[str, int]]:
        return list(self.anniversary_users)

    async def list_user_ids_with_open_entry(self, work_date) -> list[str]:
        return list(self.user_ids_with_open_entry)


class FakeEmailSender:
    def __init__(self, *, fail_for: Optional[set[str]] = None):
        self.sent: list[dict[str, Any]] = []
        self._fail_for = fail_for or set()

    async def send(
        self,
        *,
        to: str,
        template: str,
        context: dict[str, Any],
        user_id: Optional[str] = None,
    ) -> EmailResult:
        if to in self._fail_for:
            raise RuntimeError(f"Simulated email failure for {to}")
        self.sent.append({"to": to, "template": template, "context": context, "user_id": user_id})
        return EmailResult(status="sent", provider_message_id=f"fake-{uuid.uuid4()}")
