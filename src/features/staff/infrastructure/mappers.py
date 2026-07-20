from ..domain.entities import StaffMember
from .schemas import StaffMemberDTO, StaffMemberListDTO


def member_to_dto(member: StaffMember) -> StaffMemberDTO:
    return StaffMemberDTO(
        id=member.id,
        full_name=member.full_name,
        email=member.email,
        avatar_url=member.avatar_url,
        job_title=member.job_title,
        department_id=member.department_id,
        department_name=member.department_name,
        entity_id=member.entity_id,
        entity_code=member.entity_code,
        role_id=member.role_id,
        role_code=member.role_code,
        status=member.status,
        hire_date=member.hire_date,
        vacation_days_per_year=member.vacation_days_per_year,
        vacation_days_override=member.vacation_days_override,
        vacation_days_calculated=member.vacation_days_calculated,
    )


def members_to_dto(members: list[StaffMember], total: int) -> StaffMemberListDTO:
    return StaffMemberListDTO(members=[member_to_dto(m) for m in members], total=total)
