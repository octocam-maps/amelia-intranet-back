from datetime import date
from typing import Optional

import pytest

from src.features.profile.application.use_cases.get_my_profile import (
    GetMyProfileUseCase,
)
from src.features.profile.domain.entities import UserProfile
from src.features.profile.domain.errors import ProfileNotFoundError

from .fakes import FakeProfileRepository


def _profile(
    *,
    id: str = "user-1",
    email: str = "sandra@ameliahub.com",
    full_name: str = "Sandra Ramírez",
    avatar_url: Optional[str] = "https://example.com/avatar.png",
    role_code: str = "empleado",
    job_title: Optional[str] = "Project Manager",
    hire_date: Optional[date] = None,
    entity_name: Optional[str] = "Amelia Hub",
    department_name: Optional[str] = "Operaciones",
    manager_name: Optional[str] = "Beatriz Luna",
    is_external: bool = False,
) -> UserProfile:
    return UserProfile(
        id=id,
        email=email,
        full_name=full_name,
        avatar_url=avatar_url,
        role_code=role_code,
        job_title=job_title,
        hire_date=hire_date,
        entity_name=entity_name,
        department_name=department_name,
        manager_name=manager_name,
        is_external=is_external,
    )


@pytest.mark.asyncio
async def test_returns_the_profile_of_the_requesting_user():
    repository = FakeProfileRepository([_profile()])
    use_case = GetMyProfileUseCase(repository)

    profile = await use_case.execute("user-1")

    assert profile.id == "user-1"
    assert profile.entity_name == "Amelia Hub"
    assert profile.department_name == "Operaciones"
    assert profile.manager_name == "Beatriz Luna"


@pytest.mark.asyncio
async def test_raises_not_found_when_user_has_no_profile():
    repository = FakeProfileRepository([])
    use_case = GetMyProfileUseCase(repository)

    with pytest.raises(ProfileNotFoundError):
        await use_case.execute("missing-user")


@pytest.mark.asyncio
async def test_externo_invitado_profile_has_no_entity_or_department():
    repository = FakeProfileRepository(
        [
            _profile(
                id="user-2",
                role_code="externo_invitado",
                entity_name=None,
                department_name=None,
                manager_name=None,
                job_title=None,
                is_external=True,
            )
        ]
    )
    use_case = GetMyProfileUseCase(repository)

    profile = await use_case.execute("user-2")

    assert profile.role_code == "externo_invitado"
    assert profile.is_external is True
    assert profile.entity_name is None
    assert profile.department_name is None
    assert profile.manager_name is None
