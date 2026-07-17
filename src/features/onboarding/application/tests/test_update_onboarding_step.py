"""
`PATCH /onboarding/admin/steps/{step_id}` — edición parcial. `config`, si se
envía, reemplaza el JSONB entero y se valida contra el `type` del paso.
"""

import pytest

from src.features.onboarding.application.use_cases.update_onboarding_step import (
    UpdateOnboardingStepUseCase,
)
from src.features.onboarding.domain.errors import (
    InvalidStepConfigError,
    OnboardingStepNotFoundError,
)

from .fakes import FakeOnboardingRepository
from .steps import ALL_STEPS, QUIZ_STEP, VIDEO_STEP


@pytest.mark.asyncio
async def test_partial_update_keeps_untouched_fields():
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    use_case = UpdateOnboardingStepUseCase(repository)

    updated = await use_case.execute(step_id=VIDEO_STEP.id, is_active=False)

    assert updated.is_active is False
    assert updated.title == VIDEO_STEP.title
    assert updated.config == VIDEO_STEP.config


@pytest.mark.asyncio
async def test_replaces_title_and_config():
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    use_case = UpdateOnboardingStepUseCase(repository)
    new_config = {"url": "/videos/nuevo.mp4", "duration": 120}

    updated = await use_case.execute(
        step_id=VIDEO_STEP.id, title="Nuevo título", config=new_config
    )

    assert updated.title == "Nuevo título"
    assert updated.config == new_config


@pytest.mark.asyncio
async def test_rejects_quiz_config_missing_questions():
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    use_case = UpdateOnboardingStepUseCase(repository)

    with pytest.raises(InvalidStepConfigError):
        await use_case.execute(step_id=QUIZ_STEP.id, config={"threshold": 0.7})


@pytest.mark.asyncio
async def test_rejects_quiz_config_with_correct_answer_not_in_options():
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    use_case = UpdateOnboardingStepUseCase(repository)
    bad_config = {
        "threshold": 0.7,
        "questions": [
            {"id": "q1", "text": "¿?", "options": ["a", "b"], "correct": "c"}
        ],
    }

    with pytest.raises(InvalidStepConfigError):
        await use_case.execute(step_id=QUIZ_STEP.id, config=bad_config)


@pytest.mark.asyncio
async def test_rejects_video_config_without_duration():
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    use_case = UpdateOnboardingStepUseCase(repository)

    with pytest.raises(InvalidStepConfigError):
        await use_case.execute(step_id=VIDEO_STEP.id, config={"url": "/x.mp4"})


@pytest.mark.asyncio
async def test_unknown_step_raises_not_found():
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    use_case = UpdateOnboardingStepUseCase(repository)

    with pytest.raises(OnboardingStepNotFoundError):
        await use_case.execute(step_id="does-not-exist", title="x")
