from ..domain.entities import RoleChange, StaffMember
from .schemas import (
    RoleChangeDTO,
    RoleChangeListDTO,
    StaffMemberDTO,
    StaffMemberListDTO,
)


def member_to_dto(member: StaffMember) -> StaffMemberDTO:
    return StaffMemberDTO(
        id=member.id,
        full_name=member.full_name,
        email=member.email,
        avatar_url=member.avatar_url,
        job_title=member.job_title,
        contract_type=member.contract_type,
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


def role_change_to_dto(change: RoleChange) -> RoleChangeDTO:
    return RoleChangeDTO(
        id=change.id,
        from_role_code=change.from_role_code,
        to_role_code=change.to_role_code,
        changed_by_id=change.changed_by_id,
        changed_by_name=change.changed_by_name,
        changed_at=change.changed_at,
        note=change.note,
    )


def role_history_to_dto(changes: list[RoleChange]) -> RoleChangeListDTO:
    return RoleChangeListDTO(changes=[role_change_to_dto(c) for c in changes])
