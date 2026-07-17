"""
`POST /onboarding/admin/steps/{step_id}/reset-quiz` — el override que
faltaba: un empleado que suspende el cuestionario de un único intento
quedaba bloqueado para siempre. El admin borra el intento consumido y
reabre el progreso.
"""

import pytest

from datetime import datetime, timezone

from src.features.onboarding.application.use_cases.reset_quiz_attempt import (
    ResetQuizAttemptUseCase,
)
from src.features.onboarding.domain.entities import OnboardingProgress, QuizAttempt
from src.features.onboarding.domain.errors import (
    OnboardingProgressNotFoundError,
    OnboardingStepNotFoundError,
    WrongStepTypeError,
)

from .fakes import FakeOnboardingRepository
from .steps import ALL_STEPS, QUIZ_STEP, VIDEO_STEP


def _failed_quiz_progress() -> OnboardingProgress:
    return OnboardingProgress(
        id="progress-quiz",
        user_id="user-1",
        step_id=QUIZ_STEP.id,
        status="available",  # se quedó "available" tras un intento fallido
        progress_pct=0,
        data={},
        started_at=None,
        completed_at=None,
    )


@pytest.mark.asyncio
async def test_reset_deletes_attempt_and_reopens_progress():
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    repository.progress[("user-1", QUIZ_STEP.id)] = _failed_quiz_progress()
    repository.quiz_attempts[("user-1", QUIZ_STEP.id)] = QuizAttempt(
        id="attempt-1",
        user_id="user-1",
        step_id=QUIZ_STEP.id,
        answers={"q1": "5"},
        score=25.0,
        passed=False,
        submitted_at=datetime.now(timezone.utc),
    )
    use_case = ResetQuizAttemptUseCase(repository)

    reopened = await use_case.execute(step_id=QUIZ_STEP.id, user_id="user-1")

    assert reopened.status == "available"
    assert reopened.progress_pct == 0
    assert reopened.completed_at is None
    assert ("user-1", QUIZ_STEP.id) not in repository.quiz_attempts


@pytest.mark.asyncio
async def test_reset_reopens_even_a_completed_quiz_step():
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    repository.progress[("user-1", QUIZ_STEP.id)] = OnboardingProgress(
        id="progress-quiz",
        user_id="user-1",
        step_id=QUIZ_STEP.id,
        status="completed",
        progress_pct=100,
        data={"score": 100.0},
        started_at=None,
        completed_at=None,
    )
    use_case = ResetQuizAttemptUseCase(repository)

    reopened = await use_case.execute(step_id=QUIZ_STEP.id, user_id="user-1")

    assert reopened.status == "available"
    assert reopened.data == {}


@pytest.mark.asyncio
async def test_rejects_non_quiz_step():
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    use_case = ResetQuizAttemptUseCase(repository)

    with pytest.raises(WrongStepTypeError):
        await use_case.execute(step_id=VIDEO_STEP.id, user_id="user-1")


@pytest.mark.asyncio
async def test_unknown_step_raises_not_found():
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    use_case = ResetQuizAttemptUseCase(repository)

    with pytest.raises(OnboardingStepNotFoundError):
        await use_case.execute(step_id="does-not-exist", user_id="user-1")


@pytest.mark.asyncio
async def test_user_without_initialized_progress_raises_not_found():
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    use_case = ResetQuizAttemptUseCase(repository)

    with pytest.raises(OnboardingProgressNotFoundError):
        await use_case.execute(step_id=QUIZ_STEP.id, user_id="user-never-started")
