"""Fake en memoria de `IMailboxRepository` — permite testear los casos de
uso sin Postgres, igual que en `features/absences` y `features/team`."""

import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Optional

from src.features.mailbox.domain.entities import AnonymousMessage

_STATUS_BY_FILTER = {"unread": "new", "resolved": "resolved"}


class FakeMailboxRepository:
    def __init__(self, messages: Optional[list[AnonymousMessage]] = None):
        self.messages: dict[str, AnonymousMessage] = {m.id: m for m in (messages or [])}
        self._next_code = 1

    async def create_message(self, *, category: str, subject, body) -> AnonymousMessage:
        message_id = str(uuid.uuid4())
        # Espeja el reintento ante colisión de `reference_code` del
        # adaptador real, pero sin aleatoriedad (determinista para tests).
        reference_code = f"A-{self._next_code:03d}"
        self._next_code += 1
        message = AnonymousMessage(
            id=message_id,
            reference_code=reference_code,
            category=category,
            subject=subject,
            body=body,
            status="new",
            admin_reply=None,
            replied_at=None,
            created_at=datetime.now(timezone.utc),
        )
        self.messages[message_id] = message
        return message

    async def find_by_id(self, message_id: str) -> Optional[AnonymousMessage]:
        return self.messages.get(message_id)

    async def find_by_reference_code(self, reference_code: str) -> Optional[AnonymousMessage]:
        for message in self.messages.values():
            if message.reference_code == reference_code:
                return message
        return None

    async def list_messages(self, *, status_filter: Optional[str]) -> list[AnonymousMessage]:
        status = _STATUS_BY_FILTER.get(status_filter or "")
        messages = list(self.messages.values())
        if status:
            messages = [m for m in messages if m.status == status]
        return sorted(messages, key=lambda m: m.created_at, reverse=True)

    async def save_reply(self, message_id: str, *, admin_reply: str) -> Optional[AnonymousMessage]:
        existing = self.messages.get(message_id)
        if existing is None:
            return None
        updated = replace(
            existing,
            admin_reply=admin_reply,
            replied_at=datetime.now(timezone.utc),
            status="read" if existing.status == "new" else existing.status,
        )
        self.messages[message_id] = updated
        return updated

    async def mark_resolved(self, message_id: str) -> Optional[AnonymousMessage]:
        existing = self.messages.get(message_id)
        if existing is None:
            return None
        updated = replace(existing, status="resolved")
        self.messages[message_id] = updated
        return updated
