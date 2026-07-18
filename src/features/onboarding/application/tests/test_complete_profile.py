from datetime import date, timedelta

import pytest

from src.features.onboarding.application.use_cases.complete_profile import (
    CompleteProfileUseCase,
)
from src.features.onboarding.domain.entities import (
    OnboardingProgress,
    ProfileCompletionData,
)
from src.features.onboarding.domain.errors import (
    IncompleteProfileDataError,
    InvalidDepartmentError,
    OnboardingUserNotFoundError,
    StepNotAvailableForRoleError,
)

from .fakes import FakeOnboardingRepository
from .steps import ALL_STEPS, PROFILE_STEP


def _valid_profile(**overrides) -> ProfileCompletionData:
    defaults = dict(
        full_name="Sandra Ramírez",
        birth_date=date(1990, 5, 20),
        dni_nie="12345678Z",
        personal_phone="+34 600 111 222",
        address="Calle Mayor 1, Madrid",
        department_id="dept-1",
        company_phone=None,
    )
    defaults.update(overrides)
    return ProfileCompletionData(**defaults)


def _repository_with_available_profile_step(**kwargs) -> FakeOnboardingRepository:
    kwargs.setdefault("department_ids", {"dept-1"})
    repository = FakeOnboardingRepository(steps=ALL_STEPS, **kwargs)
    repository.progress[("user-1", PROFILE_STEP.id)] = OnboardingProgress(
        id="progress-profile",
        user_id="user-1",
        step_id=PROFILE_STEP.id,
        status="available",
        progress_pct=0,
        data={},
        started_at=None,
        completed_at=None,
    )
    return repository


@pytest.mark.asyncio
async def test_completes_profile_step_with_all_required_fields():
    repository = _repository_with_available_profile_step()
    use_case = CompleteProfileUseCase(repository)

    progress = await use_case.execute(
        user_id="user-1",
        role="empleado",
        step_id=PROFILE_STEP.id,
        profile=_valid_profile(),
    )

    assert progress.status == "completed"
    # Los datos reales viven en users/user_profiles, no en el JSONB de
    # progreso — ya no se duplica PII fuera de su tabla.
    assert progress.data == {}
    assert repository.saved_profiles["user-1"].dni_nie == "12345678Z"


@pytest.mark.asyncio
async def test_company_phone_is_optional():
    repository = _repository_with_available_profile_step()
    use_case = CompleteProfileUseCase(repository)

    progress = await use_case.execute(
        user_id="user-1",
        role="empleado",
        step_id=PROFILE_STEP.id,
        profile=_valid_profile(company_phone=None),
    )

    assert progress.status == "completed"
    assert repository.saved_profiles["user-1"].company_phone is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("full_name", "   "),
        ("full_name", ""),
        ("dni_nie", "   "),
        ("personal_phone", ""),
        ("address", "   "),
        ("department_id", ""),
    ],
)
async def test_rejects_a_blank_or_whitespace_only_required_field(field, value):
    repository = _repository_with_available_profile_step()
    use_case = CompleteProfileUseCase(repository)

    with pytest.raises(IncompleteProfileDataError):
        await use_case.execute(
            user_id="user-1",
            role="empleado",
            step_id=PROFILE_STEP.id,
            profile=_valid_profile(**{field: value}),
        )
    assert "user-1" not in repository.saved_profiles


@pytest.mark.asyncio
async def test_rejects_a_missing_birth_date():
    repository = _repository_with_available_profile_step()
    use_case = CompleteProfileUseCase(repository)

    with pytest.raises(IncompleteProfileDataError):
        await use_case.execute(
            user_id="user-1",
            role="empleado",
            step_id=PROFILE_STEP.id,
            profile=_valid_profile(birth_date=None),
        )


@pytest.mark.asyncio
async def test_rejects_a_birth_date_that_is_not_in_the_past():
    repository = _repository_with_available_profile_step()
    use_case = CompleteProfileUseCase(repository)

    with pytest.raises(IncompleteProfileDataError):
        await use_case.execute(
            user_id="user-1",
            role="empleado",
            step_id=PROFILE_STEP.id,
            profile=_valid_profile(birth_date=date.today() + timedelta(days=1)),
        )


@pytest.mark.asyncio
async def test_rejects_an_invalid_dni_nie_format():
    repository = _repository_with_available_profile_step()
    use_case = CompleteProfileUseCase(repository)

    with pytest.raises(IncompleteProfileDataError):
        await use_case.execute(
            user_id="user-1",
            role="empleado",
            step_id=PROFILE_STEP.id,
            profile=_valid_profile(dni_nie="not-a-dni"),
        )


@pytest.mark.asyncio
async def test_rejects_a_department_that_does_not_exist():
    repository = _repository_with_available_profile_step(department_ids=set())
    use_case = CompleteProfileUseCase(repository)

    with pytest.raises(InvalidDepartmentError):
        await use_case.execute(
            user_id="user-1",
            role="empleado",
            step_id=PROFILE_STEP.id,
            profile=_valid_profile(department_id="unknown-dept"),
        )


@pytest.mark.asyncio
async def test_does_not_complete_the_step_when_validation_fails():
    """La validación anti-vacío ocurre ANTES de marcar el paso completado —
    un payload inválido no debe dejar el progreso a medias."""
    repository = _repository_with_available_profile_step()
    use_case = CompleteProfileUseCase(repository)

    with pytest.raises(IncompleteProfileDataError):
        await use_case.execute(
            user_id="user-1",
            role="empleado",
            step_id=PROFILE_STEP.id,
            profile=_valid_profile(full_name=""),
        )

    progress = repository.progress[("user-1", PROFILE_STEP.id)]
    assert progress.status == "available"


@pytest.mark.asyncio
async def test_raises_when_the_user_no_longer_exists():
    repository = _repository_with_available_profile_step(
        missing_user_ids={"user-1"}
    )
    use_case = CompleteProfileUseCase(repository)

    with pytest.raises(OnboardingUserNotFoundError):
        await use_case.execute(
            user_id="user-1",
            role="empleado",
            step_id=PROFILE_STEP.id,
            profile=_valid_profile(),
        )


@pytest.mark.asyncio
async def test_external_guest_has_no_profile_step():
    """El externo-invitado nunca llega a tener fila de progreso para
    "perfil" (GetMyOnboardingUseCase no la inicializa) — si de todos modos
    invoca el endpoint a mano, se rechaza por rol."""
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    use_case = CompleteProfileUseCase(repository)

    with pytest.raises(StepNotAvailableForRoleError):
        await use_case.execute(
            user_id="guest-1",
            role="externo_invitado",
            step_id=PROFILE_STEP.id,
            profile=_valid_profile(),
        )
