"""Caso de uso: editar un anuncio — título, cuerpo, audiencia, fijado y
estado de publicación. Actualización parcial: solo se tocan los campos que
llegan informados."""

from typing import Optional

from src.features.notifications.application.use_cases.notify import NotifyUseCase

from ...domain.entities import Announcement
from ...domain.errors import AnnouncementNotFoundError, InvalidAudienceTargetError
from ...domain.ports import IAnnouncementRepository

_EXCLUDED_ROLE = "externo_invitado"  # docs/permisos-roles.md § Inicio: ❌ para externo


class UpdateAnnouncementUseCase:
    def __init__(self, repository: IAnnouncementRepository, notify: Optional[NotifyUseCase] = None):
        self._repository = repository
        self._notify = notify  # opcional — ver ReviewAbsenceRequestUseCase

    async def execute(
        self,
        announcement_id: str,
        *,
        title: Optional[str] = None,
        body: Optional[str] = None,
        audience: Optional[str] = None,
        entity_code: Optional[str] = None,
        role_code: Optional[str] = None,
        is_pinned: Optional[bool] = None,
        published: Optional[bool] = None,
    ) -> Announcement:
        existing = await self._repository.find_by_id(announcement_id)
        if existing is None:
            raise AnnouncementNotFoundError("El anuncio no existe.")

        entity_id: Optional[str] = None
        role_id: Optional[str] = None
        # Cambiar de audiencia a 'all' debe VACIAR entity_id/role_id, no
        # dejarlos como estaban — de ahí las banderas clear_* explícitas
        # (COALESCE no distingue "no tocar" de "vaciar").
        clear_entity = audience is not None and audience != "entity"
        clear_role = audience is not None and audience != "role"

        if audience == "entity":
            if not entity_code:
                raise InvalidAudienceTargetError("audience='entity' requiere entity_code.")
            entity_id = await self._repository.resolve_entity_id(entity_code)
            if entity_id is None:
                raise InvalidAudienceTargetError(f"La entidad '{entity_code}' no existe.")
        elif audience == "role":
            if not role_code:
                raise InvalidAudienceTargetError("audience='role' requiere role_code.")
            role_id = await self._repository.resolve_role_id(role_code)
            if role_id is None:
                raise InvalidAudienceTargetError(f"El rol '{role_code}' no existe.")

        updated = await self._repository.update(
            announcement_id,
            title=title,
            body=body,
            audience=audience,
            entity_id=entity_id,
            role_id=role_id,
            clear_entity=clear_entity,
            clear_role=clear_role,
            is_pinned=is_pinned,
            published=published,
        )
        if updated is None:
            raise AnnouncementNotFoundError("El anuncio no existe.")

        # Solo dispara en la TRANSICIÓN a publicado — si ya estaba publicado
        # y solo se edita el título/cuerpo, no se vuelve a notificar a toda
        # la plantilla por un cambio menor.
        just_published = existing.published_at is None and updated.published_at is not None
        if self._notify is not None and just_published:
            await self._notify.notify_team_excluding_role(
                _EXCLUDED_ROLE,
                type="announcement_published",
                title=f"Nuevo anuncio: {updated.title}",
                data={"announcement_id": updated.id, "url": "/inicio"},
            )

        return updated
