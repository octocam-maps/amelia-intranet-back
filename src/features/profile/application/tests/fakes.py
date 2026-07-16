"""Fake en memoria de `IProfileRepository` — permite testear el caso de uso
sin Postgres, igual que en `features/staff`."""

import dataclasses
from typing import Optional

from src.features.profile.domain.entities import UserProfile


class FakeProfileRepository:
    def __init__(self, profiles: Optional[list[UserProfile]] = None):
        self.profiles: dict[str, UserProfile] = {p.id: p for p in (profiles or [])}

    async def find_profile_by_user_id(self, user_id: str) -> Optional[UserProfile]:
        return self.profiles.get(user_id)

    async def update_profile_contact(
        self, user_id: str, *, phone: Optional[str], city: Optional[str]
    ) -> Optional[UserProfile]:
        # Mismo criterio PATCH que el repositorio real: `None` no toca la
        # columna (no la vacía).
        current = self.profiles.get(user_id)
        if current is None:
            return None
        updated = dataclasses.replace(
            current,
            phone=phone if phone is not None else current.phone,
            city=city if city is not None else current.city,
        )
        self.profiles[user_id] = updated
        return updated
