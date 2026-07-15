from ..domain.entities import TeamBirthday, TeamMember, VacationCalendarEntry
from .schemas import (
    TeamBirthdayDTO,
    TeamBirthdaysDTO,
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


def birthday_to_dto(birthday: TeamBirthday) -> TeamBirthdayDTO:
    return TeamBirthdayDTO(
        user_id=birthday.user_id,
        full_name=birthday.full_name,
        avatar_url=birthday.avatar_url,
        day=birthday.day,
        month=birthday.month,
        is_today=birthday.is_today,
    )


def birthdays_to_dto(birthdays: list[TeamBirthday]) -> TeamBirthdaysDTO:
    return TeamBirthdaysDTO(birthdays=[birthday_to_dto(b) for b in birthdays])
