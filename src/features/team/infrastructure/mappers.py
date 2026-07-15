from ..domain.entities import TeamMember, VacationCalendarEntry
from .schemas import (
    TeamDirectoryDTO,
    TeamMemberDTO,
    VacationCalendarDTO,
    VacationCalendarEntryDTO,
)


def member_to_dto(member: TeamMember) -> TeamMemberDTO:
    return TeamMemberDTO(
        id=member.id,
        full_name=member.full_name,
        job_title=member.job_title,
        entity_code=member.entity_code,
        entity_name=member.entity_name,
        phone=member.phone,
        email=member.email,
        avatar_url=member.avatar_url,
    )


def directory_to_dto(members: list[TeamMember]) -> TeamDirectoryDTO:
    return TeamDirectoryDTO(members=[member_to_dto(m) for m in members])


def calendar_entry_to_dto(entry: VacationCalendarEntry) -> VacationCalendarEntryDTO:
    return VacationCalendarEntryDTO(
        user_id=entry.user_id,
        full_name=entry.full_name,
        start_date=entry.start_date,
        end_date=entry.end_date,
    )


def vacation_calendar_to_dto(entries: list[VacationCalendarEntry]) -> VacationCalendarDTO:
    return VacationCalendarDTO(entries=[calendar_entry_to_dto(e) for e in entries])
