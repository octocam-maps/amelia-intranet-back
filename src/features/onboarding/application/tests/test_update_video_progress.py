from dataclasses import replace

import pytest

from src.features.onboarding.application.use_cases.update_video_progress import (
    UpdateVideoProgressUseCase,
)
from src.features.onboarding.domain.entities import OnboardingProgress
from src.features.onboarding.domain.errors import (
    InvalidVideoProgressError,
    StepLockedError,
    WrongStepTypeError,
)

from .fakes import FakeOnboardingRepository
from .steps import ALL_STEPS, MANUAL_STEP, QUIZ_STEP, VIDEO_STEP


def _repository_with_available_video() -> FakeOnboardingRepository:
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    repository.progress[("user-1", VIDEO_STEP.id)] = OnboardingProgress(
        id="progress-video",
        user_id="user-1",
        step_id=VIDEO_STEP.id,
        status="available",
        progress_pct=0,
        data={},
        started_at=None,
        completed_at=None,
    )
    return repository


@pytest.mark.asyncio
async def test_rejects_report_on_a_locked_step():
    """Bloqueo secuencial validado en el backend: aunque se llame al
    endpoint a mano con el step_id del vídeo, si ese paso está `locked`
    (caso hipotético — en la práctica el vídeo siempre nace `available`,
    pero la regla de dominio no debe asumirlo) se rechaza."""
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    repository.progress[("user-1", VIDEO_STEP.id)] = OnboardingProgress(
        id="progress-video",
        user_id="user-1",
        step_id=VIDEO_STEP.id,
        status="locked",
        progress_pct=0,
        data={},
        started_at=None,
        completed_at=None,
    )
    use_case = UpdateVideoProgressUseCase(repository)

    with pytest.raises(StepLockedError):
        await use_case.execute(
            user_id="user-1", role="empleado", step_id=VIDEO_STEP.id, new_pct=10
        )


@pytest.mark.asyncio
async def test_rejects_jump_from_zero_to_hundred():
    """El caso explícito del requerimiento: un salto de golpe de 0 a 100 es
    un intento de saltar el vídeo sin verlo — se rechaza."""
    repository = _repository_with_available_video()
    use_case = UpdateVideoProgressUseCase(repository)

    with pytest.raises(InvalidVideoProgressError):
        await use_case.execute(
            user_id="user-1", role="empleado", step_id=VIDEO_STEP.id, new_pct=100
        )

    # No se aplicó ningún cambio.
    assert repository.progress[("user-1", VIDEO_STEP.id)].progress_pct == 0


@pytest.mark.asyncio
async def test_rejects_progress_regression():
    repository = _repository_with_available_video()
    repository.progress[("user-1", VIDEO_STEP.id)] = replace(
        repository.progress[("user-1", VIDEO_STEP.id)],
        progress_pct=50,
        status="in_progress",
    )
    use_case = UpdateVideoProgressUseCase(repository)

    with pytest.raises(InvalidVideoProgressError):
        await use_case.execute(
            user_id="user-1", role="empleado", step_id=VIDEO_STEP.id, new_pct=20
        )


@pytest.mark.asyncio
async def test_accepts_gradual_progress_and_completes_at_100_unlocking_next_step():
    repository = _repository_with_available_video()
    repository.progress[("user-1", QUIZ_STEP.id)] = OnboardingProgress(
        id="progress-quiz",
        user_id="user-1",
        step_id=QUIZ_STEP.id,
        status="locked",
        progress_pct=0,
        data={},
        started_at=None,
        completed_at=None,
    )
    use_case = UpdateVideoProgressUseCase(repository)

    progress = await use_case.execute(
        user_id="user-1", role="empleado", step_id=VIDEO_STEP.id, new_pct=25
    )
    assert progress.status == "in_progress"

    progress = await use_case.execute(
        user_id="user-1", role="empleado", step_id=VIDEO_STEP.id, new_pct=50
    )
    assert progress.status == "in_progress"

    progress = await use_case.execute(
        user_id="user-1", role="empleado", step_id=VIDEO_STEP.id, new_pct=75
    )
    assert progress.status == "in_progress"

    progress = await use_case.execute(
        user_id="user-1", role="empleado", step_id=VIDEO_STEP.id, new_pct=100
    )
    assert progress.status == "completed"
    assert progress.completed_at is not None

    # El siguiente paso (quiz, order 2) queda desbloqueado.
    quiz_progress = repository.progress[("user-1", QUIZ_STEP.id)]
    assert quiz_progress.status == "available"


@pytest.mark.asyncio
async def test_external_guest_completing_video_unlocks_manual_not_quiz():
    """Regresión: el desbloqueo NO puede asumir `step_order + 1` a secas —
    el externo-invitado no tiene fila de progreso para "quiz" (order 2), así
    que el siguiente paso real tras el vídeo es "manual" (order 4)."""
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    await repository.ensure_progress_initialized(
        "guest-1",
        [
            VIDEO_STEP,
            MANUAL_STEP,
        ],  # mismo filtrado que aplicaría GetMyOnboardingUseCase
    )
    use_case = UpdateVideoProgressUseCase(repository)

    for pct in (30, 60, 90, 100):
        await use_case.execute(
            user_id="guest-1",
            role="externo_invitado",
            step_id=VIDEO_STEP.id,
            new_pct=pct,
        )

    manual_progress = repository.progress[("guest-1", MANUAL_STEP.id)]
    assert manual_progress.status == "available"
    assert ("guest-1", QUIZ_STEP.id) not in repository.progress


@pytest.mark.asyncio
async def test_wrong_step_type_is_rejected():
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    repository.progress[("user-1", QUIZ_STEP.id)] = OnboardingProgress(
        id="progress-quiz",
        user_id="user-1",
        step_id=QUIZ_STEP.id,
        status="available",
        progress_pct=0,
        data={},
        started_at=None,
        completed_at=None,
    )
    use_case = UpdateVideoProgressUseCase(repository)

    with pytest.raises(WrongStepTypeError):
        await use_case.execute(
            user_id="user-1", role="empleado", step_id=QUIZ_STEP.id, new_pct=10
        )
