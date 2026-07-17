"""Caso de uso: obtener la ficha de "Mi perfil" del usuario autenticado.
RGPD: siempre se resuelve por el `user_id` del token — nunca por un id de
la URL — así que no admite `target_user_id` (a diferencia de
`GetAbsenceBalanceUseCase`, aquí no hay caso admin-ve-de-otro)."""

from ...domain.entities import UserProfile
from ...domain.errors import ProfileNotFoundError
from ...domain.ports import IProfileRepository


class GetMyProfileUseCase:
    def __init__(self, repository: IProfileRepository):
        self._repository = repository

    async def execute(self, user_id: str) -> UserProfile:
        profile = await self._repository.find_profile_by_user_id(user_id)
        if profile is None:
            raise ProfileNotFoundError("No se encontró el perfil del usuario.")
        return profile
