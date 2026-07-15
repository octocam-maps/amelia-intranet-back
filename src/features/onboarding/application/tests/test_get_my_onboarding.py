import pytest

from src.features.onboarding.application.use_cases.get_my_onboarding import (
    GetMyOnboardingUseCase,
)

from .fakes import FakeOnboardingRepository
from .steps import ALL_STEPS, MANUAL_STEP, VIDEO_STEP


@pytest.mark.asyncio
async def test_first_visit_initializes_progress_first_step_available_rest_locked():
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    use_case = GetMyOnboardingUseCase(repository)

    pairs = await use_case.execute(user_id="user-1", role="empleado")

    assert [step.id for step, _ in pairs] == [s.id for s in ALL_STEPS]
    statuses = {step.id: progress.status for step, progress in pairs}
    assert statuses[VIDEO_STEP.id] == "available"
    assert all(
        status == "locked"
        for step_id, status in statuses.items()
        if step_id != VIDEO_STEP.id
    )


@pytest.mark.asyncio
async def test_second_visit_does_not_reset_progress():
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    use_case = GetMyOnboardingUseCase(repository)

    await use_case.execute(user_id="user-1", role="empleado")
    # El usuario avanza "a mano" en el fake (simula progreso ya hecho).
    key = ("user-1", VIDEO_STEP.id)
    from dataclasses import replace

    repository.progress[key] = replace(
        repository.progress[key], status="completed", progress_pct=100
    )

    pairs = await use_case.execute(user_id="user-1", role="empleado")
    video_progress = next(p for step, p in pairs if step.id == VIDEO_STEP.id)
    assert video_progress.status == "completed"


@pytest.mark.asyncio
async def test_external_guest_only_gets_video_and_manual_steps():
    """docs/permisos-roles.md § Onboarding: el externo-invitado hace
    onboarding parcial — sin firma, cuestionario ni perfil."""
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    use_case = GetMyOnboardingUseCase(repository)

    pairs = await use_case.execute(user_id="guest-1", role="externo_invitado")

    step_ids = {step.id for step, _ in pairs}
    assert step_ids == {VIDEO_STEP.id, MANUAL_STEP.id}


@pytest.mark.asyncio
async def test_external_guest_manual_step_starts_locked_video_is_available():
    """El "primero" del externo-invitado (por step_order) es el vídeo — el
    manual (order 4) nace `locked` aunque el cuestionario/firma que están
    entre medias ni siquiera existan para su rol."""
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    use_case = GetMyOnboardingUseCase(repository)

    pairs = await use_case.execute(user_id="guest-1", role="externo_invitado")

    statuses = {step.id: progress.status for step, progress in pairs}
    assert statuses[VIDEO_STEP.id] == "available"
    assert statuses[MANUAL_STEP.id] == "locked"
