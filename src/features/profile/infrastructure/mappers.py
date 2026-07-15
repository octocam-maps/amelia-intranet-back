from ..domain.entities import UserProfile
from .schemas import ProfileDTO


def profile_to_dto(profile: UserProfile) -> ProfileDTO:
    return ProfileDTO(
        id=profile.id,
        email=profile.email,
        full_name=profile.full_name,
        avatar_url=profile.avatar_url,
        role=profile.role_code,
        job_title=profile.job_title,
        hire_date=profile.hire_date,
        entity_name=profile.entity_name,
        department_name=profile.department_name,
        manager_name=profile.manager_name,
        is_external=profile.is_external,
    )
