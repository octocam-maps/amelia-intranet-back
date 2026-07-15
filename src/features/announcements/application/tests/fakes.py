"""Fake en memoria de `IAnnouncementRepository` — permite testear los casos
de uso sin Postgres, igual que en `features/mailbox`/`features/staff`."""

import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Optional

from src.features.announcements.domain.entities import Announcement

_ENTITY_IDS = {"hub": "entity-hub", "lab": "entity-lab", "ops": "entity-ops"}
_ROLE_IDS = {
    "administrador": "role-administrador",
    "empleado": "role-empleado",
    "externo_invitado": "role-externo_invitado",
}


class FakeAnnouncementRepository:
    def __init__(self, announcements: Optional[list[Announcement]] = None):
        self.announcements: dict[str, Announcement] = {
            a.id: a for a in (announcements or [])
        }

    async def list_all(self) -> list[Announcement]:
        items = list(self.announcements.values())
        return sorted(items, key=lambda a: (not a.is_pinned, a.created_at), reverse=False)

    async def list_feed(
        self, *, role_code: str, entity_id: Optional[str], limit: Optional[int]
    ) -> list[Announcement]:
        def _applies(a: Announcement) -> bool:
            if a.published_at is None:
                return False
            if a.audience == "all":
                return True
            if a.audience == "entity":
                return a.entity_id == entity_id
            if a.audience == "role":
                return a.role_code == role_code
            return False

        items = [a for a in self.announcements.values() if _applies(a)]
        items.sort(key=lambda a: (a.is_pinned, a.published_at), reverse=True)
        return items[:limit] if limit else items

    async def find_by_id(self, announcement_id: str) -> Optional[Announcement]:
        return self.announcements.get(announcement_id)

    async def resolve_entity_id(self, entity_code: str) -> Optional[str]:
        return _ENTITY_IDS.get(entity_code)

    async def resolve_role_id(self, role_code: str) -> Optional[str]:
        return _ROLE_IDS.get(role_code)

    async def create(
        self,
        *,
        title,
        body,
        author_id,
        audience,
        entity_id,
        role_id,
        is_pinned,
        published_at,
    ) -> Announcement:
        announcement_id = str(uuid.uuid4())
        entity_code = next((k for k, v in _ENTITY_IDS.items() if v == entity_id), None)
        role_code = next((k for k, v in _ROLE_IDS.items() if v == role_id), None)
        announcement = Announcement(
            id=announcement_id,
            title=title,
            body=body,
            author_id=author_id,
            author_full_name="Beatriz Luna",
            audience=audience,
            entity_id=entity_id,
            entity_code=entity_code,
            role_id=role_id,
            role_code=role_code,
            is_pinned=is_pinned,
            published_at=published_at,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.announcements[announcement_id] = announcement
        return announcement

    async def update(
        self,
        announcement_id,
        *,
        title,
        body,
        audience,
        entity_id,
        role_id,
        clear_entity,
        clear_role,
        is_pinned,
        published,
    ) -> Optional[Announcement]:
        existing = self.announcements.get(announcement_id)
        if existing is None:
            return None

        new_entity_id = None if clear_entity else (entity_id or existing.entity_id)
        new_role_id = None if clear_role else (role_id or existing.role_id)
        new_entity_code = next((k for k, v in _ENTITY_IDS.items() if v == new_entity_id), None)
        new_role_code = next((k for k, v in _ROLE_IDS.items() if v == new_role_id), None)

        published_at = existing.published_at
        if published is True and published_at is None:
            published_at = datetime.now(timezone.utc)
        elif published is False:
            published_at = None

        updated = replace(
            existing,
            title=title if title is not None else existing.title,
            body=body if body is not None else existing.body,
            audience=audience if audience is not None else existing.audience,
            entity_id=new_entity_id,
            entity_code=new_entity_code,
            role_id=new_role_id,
            role_code=new_role_code,
            is_pinned=is_pinned if is_pinned is not None else existing.is_pinned,
            published_at=published_at,
            updated_at=datetime.now(timezone.utc),
        )
        self.announcements[announcement_id] = updated
        return updated

    async def soft_delete(self, announcement_id: str) -> bool:
        if announcement_id not in self.announcements:
            return False
        del self.announcements[announcement_id]
        return True
