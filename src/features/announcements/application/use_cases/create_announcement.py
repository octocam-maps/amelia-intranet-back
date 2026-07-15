"""Caso de uso: crear/publicar un anuncio (exclusivo del admin,
docs/permisos-roles.md § "Anuncios": "Crear / publicar" es una sola acción —
no hay flujo de borrador separado todavía)."""

from datetime import datetime, timezone
from typing import Optional

from src.features.notifications.application.use_cases.notify import NotifyUseCase

from ...domain.entities import Announcement
from ...domain.errors import InvalidAudienceTargetError
from ...domain.ports import IAnnouncementRepository


class CreateAnnouncementUseCase:
    def __init__(self, repository: IAnnouncementRepository, notify: Optional[NotifyUseCase] = None):
        self._repository = repository
        self._notify = notify  # opcional — ver ReviewAbsenceRequestUseCase

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

        announcement = await self._repository.create(
            title=title,
            body=body,
            author_id=author_id,
            audience=audience,
            entity_id=entity_id,
            role_id=role_id,
            is_pinned=is_pinned,
            published_at=datetime.now(timezone.utc) if published else None,
        )

        # El aviso respeta la MISMA audiencia que el anuncio (all/entity/
        # role) — un anuncio "solo Hub" no debe notificar a Lab/Ops, aunque
        # externo_invitado quede excluido siempre.
        if self._notify is not None and announcement.published_at is not None:
            await self._notify.notify_announcement(
                audience=audience,
                entity_id=entity_id,
                role_id=role_id,
                type="announcement_published",
                title=f"Nuevo anuncio: {announcement.title}",
                data={"announcement_id": announcement.id, "url": "/"},
            )

        return announcement
