"""Caso de uso: borrar un anuncio (exclusivo del admin). Soft-delete —
`announcements.deleted_at` (005_admin_comms.sql) — desaparece del feed y de
la gestión sin perder el histórico."""

from ...domain.errors import AnnouncementNotFoundError
from ...domain.ports import IAnnouncementRepository


class DeleteAnnouncementUseCase:
    def __init__(self, repository: IAnnouncementRepository):
        self._repository = repository

    async def execute(self, announcement_id: str) -> None:
        deleted = await self._repository.soft_delete(announcement_id)
        if not deleted:
            raise AnnouncementNotFoundError("El anuncio no existe.")
