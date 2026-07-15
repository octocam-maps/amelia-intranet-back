"""Fake en memoria de `IProfileRepository` — permite testear el caso de uso
sin Postgres, igual que en `features/staff`."""

from typing import Optional

from src.features.profile.domain.entities import UserProfile


class FakeProfileRepository:
    def __init__(self, profiles: Optional[list[UserProfile]] = None):
        self.profiles: dict[str, UserProfile] = {p.id: p for p in (profiles or [])}

    async def find_profile_by_user_id(self, user_id: str) -> Optional[UserProfile]:
        return self.profiles.get(user_id)
