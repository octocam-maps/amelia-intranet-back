from datetime import date
from typing import Optional

import pytest

from src.features.profile.application.use_cases.update_my_profile import (
    UpdateMyProfileUseCase,
)
from src.features.profile.domain.entities import UserProfile
from src.features.profile.domain.errors import ProfileNotFoundError

from .fakes import FakeProfileRepository


def _profile(
    *,
    id: str = "user-1",
    phone: Optional[str] = "+34 600 111 222",
    city: Optional[str] = "Madrid",
) -> UserProfile:
    return UserProfile(
        id=id,
        email="sandra@ameliahub.com",
        full_name="Sandra Ramírez",
        avatar_url=None,
        role_code="empleado",
        job_title="Project Manager",
        hire_date=date(2022, 3, 1),
        entity_name="Amelia Hub",
        department_name="Operaciones",
        manager_name="Beatriz Luna",
        is_external=False,
        phone=phone,
        city=city,
    )


@pytest.mark.asyncio
async def test_updates_the_phone_and_city_of_the_requesting_user():
    repository = FakeProfileRepository([_profile(phone=None, city=None)])
    use_case = UpdateMyProfileUseCase(repository)

    profile = await use_case.execute(
        "user-1", phone="+34 611 222 333", city="Valencia"
    )

    assert profile.phone == "+34 611 222 333"
    assert profile.city == "Valencia"


@pytest.mark.asyncio
async def test_partial_update_does_not_clear_the_field_left_out():
    """Semántica PATCH: si solo llega `city`, `phone` se mantiene tal cual
    estaba (no se vacía) — mismo criterio que `UpdateStaffMemberUseCase`."""
    repository = FakeProfileRepository([_profile(phone="+34 600 111 222", city="Madrid")])
    use_case = UpdateMyProfileUseCase(repository)

    profile = await use_case.execute("user-1", city="Sevilla")

    assert profile.city == "Sevilla"
    assert profile.phone == "+34 600 111 222"


@pytest.mark.asyncio
async def test_raises_not_found_when_user_has_no_profile():
    repository = FakeProfileRepository([])
    use_case = UpdateMyProfileUseCase(repository)

    with pytest.raises(ProfileNotFoundError):
        await use_case.execute("missing-user", phone="+34 600 000 000")
