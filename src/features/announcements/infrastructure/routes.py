"""
Router de `/announcements`: tablón de anuncios (docs/permisos-roles.md §
"Anuncios" — el admin crea/publica, el resto solo lee). Ampliación de
alcance aprobada por el team-lead: el externo-invitado ahora tiene un
"Inicio" recortado en la WEB con la tarjeta de Anuncios en solo lectura
(mismo feed que `empleado`, filtrado por audiencia) — sigue sin poder
crear/editar/borrar.

Un único `GET` sirve tanto a la tarjeta del dashboard (`empleado`/`socio`/
`externo_invitado`, con `limit`) como a la gestión del admin (sin filtrar
por audiencia) — así lo pidió el frontend para no duplicar contrato.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.shared.auth.dependencies import require_role

from ..application.use_cases.create_announcement import CreateAnnouncementUseCase
from ..application.use_cases.delete_announcement import DeleteAnnouncementUseCase
from ..application.use_cases.list_announcements import ListAnnouncementsUseCase
from ..application.use_cases.update_announcement import UpdateAnnouncementUseCase
from .dependencies import (
    get_create_announcement_use_case,
    get_delete_announcement_use_case,
    get_list_announcements_use_case,
    get_update_announcement_use_case,
)
from .mappers import announcement_to_dto, announcements_to_dto
from .schemas import AnnouncementDTO, AnnouncementListDTO, CreateAnnouncementDTO, UpdateAnnouncementDTO


def create_announcements_router() -> APIRouter:
    router = APIRouter(prefix="/announcements", tags=["announcements"])

    @router.get("", response_model=AnnouncementListDTO)
    async def list_announcements(
        limit: Optional[int] = Query(None, ge=1, le=50),
        # `socio` [migración 024] = igual que empleado en TODA la app — lee
        # el tablón igual que cualquier empleado, sigue sin poder publicar.
        # `externo_invitado` [ampliación de alcance, ver Inicio recortado en
        # amelia-intranet-web] = solo lectura del feed, misma regla de
        # audiencia que el resto — sigue sin poder publicar/editar/borrar.
        current_user: dict = Depends(
            require_role("administrador", "empleado", "socio", "externo_invitado")
        ),
        use_case: ListAnnouncementsUseCase = Depends(get_list_announcements_use_case),
    ):
        announcements = await use_case.execute(
            requester_role=current_user["role"],
            requester_entity_id=current_user.get("entity_id"),
            limit=limit,
        )
        return announcements_to_dto(announcements)

    @router.post("", response_model=AnnouncementDTO, status_code=201)
    async def create_announcement(
        dto: CreateAnnouncementDTO,
        current_user: dict = Depends(require_role("administrador")),
        use_case: CreateAnnouncementUseCase = Depends(get_create_announcement_use_case),
    ):
        announcement = await use_case.execute(
            title=dto.title,
            body=dto.body,
            author_id=current_user["sub"],
            audience=dto.audience,
            entity_code=dto.entity,
            role_code=dto.role,
            is_pinned=dto.is_pinned,
            published=dto.published,
        )
        return announcement_to_dto(announcement)

    @router.patch("/{announcement_id}", response_model=AnnouncementDTO)
    async def update_announcement(
        announcement_id: str,
        dto: UpdateAnnouncementDTO,
        current_user: dict = Depends(require_role("administrador")),
        use_case: UpdateAnnouncementUseCase = Depends(get_update_announcement_use_case),
    ):
        announcement = await use_case.execute(
            announcement_id,
            title=dto.title,
            body=dto.body,
            audience=dto.audience,
            entity_code=dto.entity,
            role_code=dto.role,
            is_pinned=dto.is_pinned,
            published=dto.published,
        )
        return announcement_to_dto(announcement)

    @router.delete("/{announcement_id}", status_code=204)
    async def delete_announcement(
        announcement_id: str,
        current_user: dict = Depends(require_role("administrador")),
        use_case: DeleteAnnouncementUseCase = Depends(get_delete_announcement_use_case),
    ):
        await use_case.execute(announcement_id)

    return router
