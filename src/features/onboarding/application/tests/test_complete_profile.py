import pytest

from src.features.onboarding.application.use_cases.complete_profile import (
    CompleteProfileUseCase,
)
from src.features.onboarding.domain.entities import OnboardingProgress
from src.features.onboarding.domain.errors import StepNotAvailableForRoleError

from .fakes import FakeOnboardingRepository
from .steps import ALL_STEPS, PROFILE_STEP


@pytest.mark.asyncio
async def test_completes_profile_step_with_draft_payload():
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
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
    use_case = CompleteProfileUseCase(repository)

    progress = await use_case.execute(
        user_id="user-1",
        role="empleado",
        step_id=PROFILE_STEP.id,
        data={"phone": "600111222"},
    )

    assert progress.status == "completed"
    assert progress.data == {"phone": "600111222"}


@pytest.mark.asyncio
async def test_external_guest_has_no_profile_step():
    """El externo-invitado nunca llega a tener fila de progreso para
    "perfil" (GetMyOnboardingUseCase no la inicializa) — si de todos modos
    invoca el endpoint a mano, se rechaza por rol."""
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    use_case = CompleteProfileUseCase(repository)

    with pytest.raises(StepNotAvailableForRoleError):
        await use_case.execute(
            user_id="guest-1", role="externo_invitado", step_id=PROFILE_STEP.id, data={}
        )
