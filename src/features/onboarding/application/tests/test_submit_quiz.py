import pytest

from src.features.onboarding.application.use_cases.submit_quiz import SubmitQuizUseCase
from src.features.onboarding.domain.entities import OnboardingProgress
from src.features.onboarding.domain.errors import (
    QuizAlreadyAttemptedError,
    StepNotAvailableForRoleError,
)

from .fakes import FakeOnboardingRepository
from .steps import ALL_STEPS, QUIZ_STEP, SIGNATURE_STEP


def _repository_with_available_quiz() -> FakeOnboardingRepository:
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
    return repository


_PASSING_ANSWERS = {"q1": "7", "q2": "15s", "q3": "100", "q4": "Starlink"}
_FAILING_ANSWERS = {"q1": "5", "q2": "5s", "q3": "50", "q4": "4G"}


@pytest.mark.asyncio
async def test_passing_score_completes_step_and_unlocks_next():
    repository = _repository_with_available_quiz()
    repository.progress[("user-1", SIGNATURE_STEP.id)] = OnboardingProgress(
        id="progress-signature",
        user_id="user-1",
        step_id=SIGNATURE_STEP.id,
        status="locked",
        progress_pct=0,
        data={},
        started_at=None,
        completed_at=None,
    )
    use_case = SubmitQuizUseCase(repository)

    attempt = await use_case.execute(
        user_id="user-1",
        role="empleado",
        step_id=QUIZ_STEP.id,
        answers=_PASSING_ANSWERS,
    )

    assert attempt.passed is True
    assert attempt.score == 100.0
    assert repository.progress[("user-1", QUIZ_STEP.id)].status == "completed"
    assert repository.progress[("user-1", SIGNATURE_STEP.id)].status == "available"


@pytest.mark.asyncio
async def test_failing_score_does_not_complete_step():
    repository = _repository_with_available_quiz()
    use_case = SubmitQuizUseCase(repository)

    attempt = await use_case.execute(
        user_id="user-1",
        role="empleado",
        step_id=QUIZ_STEP.id,
        answers=_FAILING_ANSWERS,
    )

    assert attempt.passed is False
    assert repository.progress[("user-1", QUIZ_STEP.id)].status == "available"


@pytest.mark.asyncio
async def test_second_attempt_is_rejected_single_attempt_enforced():
    """Intento único — la garantía real es `UNIQUE(user_id, step_id)` en
    BD, aquí espejada por el fake repository."""
    repository = _repository_with_available_quiz()
    use_case = SubmitQuizUseCase(repository)

    await use_case.execute(
        user_id="user-1",
        role="empleado",
        step_id=QUIZ_STEP.id,
        answers=_FAILING_ANSWERS,
    )

    with pytest.raises(QuizAlreadyAttemptedError):
        await use_case.execute(
            user_id="user-1",
            role="empleado",
            step_id=QUIZ_STEP.id,
            answers=_PASSING_ANSWERS,
        )


@pytest.mark.asyncio
async def test_external_guest_cannot_submit_quiz():
    """docs/permisos-roles.md § Onboarding: el externo-invitado no tiene
    cuestionario en su onboarding parcial — se rechaza en el backend aunque
    invoque el endpoint a mano."""
    repository = _repository_with_available_quiz()
    use_case = SubmitQuizUseCase(repository)

    with pytest.raises(StepNotAvailableForRoleError):
        await use_case.execute(
            user_id="guest-1",
            role="externo_invitado",
            step_id=QUIZ_STEP.id,
            answers=_PASSING_ANSWERS,
        )

    # Ni siquiera se registró el intento.
    assert ("guest-1", QUIZ_STEP.id) not in repository.quiz_attempts
