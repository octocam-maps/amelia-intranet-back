import pytest

from src.features.onboarding.application.use_cases.acknowledge_manual import (
    AcknowledgeManualUseCase,
)
from src.features.onboarding.domain.entities import OnboardingProgress

from .fakes import FakeOnboardingRepository
from .steps import ALL_STEPS, MANUAL_DOCUMENT, MANUAL_STEP


@pytest.mark.asyncio
async def test_external_guest_can_acknowledge_manual_and_complete_step():
    """El manual es uno de los dos pasos que sí tiene el onboarding parcial
    del externo-invitado (docs/permisos-roles.md § Onboarding)."""
    repository = FakeOnboardingRepository(steps=ALL_STEPS, documents=[MANUAL_DOCUMENT])
    repository.progress[("guest-1", MANUAL_STEP.id)] = OnboardingProgress(
        id="progress-manual",
        user_id="guest-1",
        step_id=MANUAL_STEP.id,
        status="available",
        progress_pct=0,
        data={},
        started_at=None,
        completed_at=None,
    )
    use_case = AcknowledgeManualUseCase(repository)

    acknowledgement = await use_case.execute(
        user_id="guest-1",
        role="externo_invitado",
        step_id=MANUAL_STEP.id,
        ip_address="203.0.113.7",
    )

    assert acknowledgement.document_id == MANUAL_DOCUMENT.id
    assert repository.progress[("guest-1", MANUAL_STEP.id)].status == "completed"
