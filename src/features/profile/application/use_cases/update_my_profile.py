"""Caso de uso: editar los datos de contacto propios (teléfono, ciudad) de
"Mi perfil". RGPD: el `user_id` SIEMPRE viene del token — a diferencia de
`UpdateStaffMemberUseCase` (admin editando a un tercero por id de URL), este
caso de uso no admite ningún `target_user_id`; solo existe "editar lo mío"."""

from typing import Optional

from ...domain.entities import UserProfile
from ...domain.errors import ProfileNotFoundError
from ...domain.ports import IProfileRepository


class UpdateMyProfileUseCase:
    def __init__(self, repository: IProfileRepository):
        self._repository = repository

    async def execute(
        self,
        user_id: str,
        *,
        phone: Optional[str] = None,
        city: Optional[str] = None,
    ) -> UserProfile:
        updated = await self._repository.update_profile_contact(
            user_id, phone=phone, city=city
        )
        if updated is None:
            raise ProfileNotFoundError("No se encontró el perfil del usuario.")
        return updated
