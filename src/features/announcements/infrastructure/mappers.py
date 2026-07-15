from ..domain.entities import Announcement
from .schemas import AnnouncementDTO, AnnouncementListDTO


def announcement_to_dto(announcement: Announcement) -> AnnouncementDTO:
    return AnnouncementDTO(
        id=announcement.id,
        title=announcement.title,
        body=announcement.body,
        author_id=announcement.author_id,
        author_full_name=announcement.author_full_name,
        audience=announcement.audience,
        entity_id=announcement.entity_id,
        entity_code=announcement.entity_code,
        role_id=announcement.role_id,
        role_code=announcement.role_code,
        is_pinned=announcement.is_pinned,
        published_at=announcement.published_at,
        created_at=announcement.created_at,
        updated_at=announcement.updated_at,
    )


def announcements_to_dto(announcements: list[Announcement]) -> AnnouncementListDTO:
    return AnnouncementListDTO(
        announcements=[announcement_to_dto(a) for a in announcements]
    )
