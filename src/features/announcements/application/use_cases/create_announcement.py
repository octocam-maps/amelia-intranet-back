"""Caso de uso: crear/publicar un anuncio (exclusivo del admin,
docs/permisos-roles.md § "Anuncios": "Crear / publicar" es una sola acción —
no hay flujo de borrador separado todavía)."""

from datetime import datetime, timezone
from typing import Optional

from ...domain.entities import Announcement
from ...domain.errors import InvalidAudienceTargetError
from ...domain.ports import IAnnouncementRepository


class CreateAnnouncementUseCase:
    def __init__(self, repository: IAnnouncementRepository):
        self._repository = repository

    async def execute(
        self,
        *,
        title: str,
        body: str,
        author_id: str,
        audience: str,
        entity_code: Optional[str],
        role_code: Optional[str],
        is_pinned: bool,
        published: bool,
    ) -> Announcement:
        entity_id: Optional[str] = None
        role_id: Optional[str] = None

        if audience == "entity":
            if not entity_code:
                raise InvalidAudienceTargetError(
                    "audience='entity' requiere entity_code."
                )
            entity_id = await self._repository.resolve_entity_id(entity_code)
            if entity_id is None:
                raise InvalidAudienceTargetError(f"La entidad '{entity_code}' no existe.")
        elif audience == "role":
            if not role_code:
                raise InvalidAudienceTargetError("audience='role' requiere role_code.")
            role_id = await self._repository.resolve_role_id(role_code)
            if role_id is None:
                raise InvalidAudienceTargetError(f"El rol '{role_code}' no existe.")

        return await self._repository.create(
            title=title,
            body=body,
            author_id=author_id,
            audience=audience,
            entity_id=entity_id,
            role_id=role_id,
            is_pinned=is_pinned,
            published_at=datetime.now(timezone.utc) if published else None,
        )
