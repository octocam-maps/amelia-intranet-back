"""
`GET /onboarding/admin/steps` — a diferencia de `GET /onboarding/me`, el
admin ve el catálogo COMPLETO (incluidos pasos `is_active=False`) y la
respuesta correcta del quiz sin enmascarar.
"""

from dataclasses import replace

import pytest

from src.features.onboarding.application.use_cases.list_onboarding_steps_admin import (
    ListOnboardingStepsForAdminUseCase,
)

from .fakes import FakeOnboardingRepository
from .steps import ALL_STEPS, QUIZ_STEP


@pytest.mark.asyncio
async def test_admin_sees_full_catalog_including_inactive_steps():
    inactive_manual = replace(ALL_STEPS[3], is_active=False)
    steps = [ALL_STEPS[0], ALL_STEPS[1], ALL_STEPS[2], inactive_manual, ALL_STEPS[4]]
    repository = FakeOnboardingRepository(steps=steps)
    use_case = ListOnboardingStepsForAdminUseCase(repository)

    result = await use_case.execute()

    assert [s.id for s in result] == [s.id for s in ALL_STEPS]
    assert next(s for s in result if s.id == inactive_manual.id).is_active is False


@pytest.mark.asyncio
async def test_admin_sees_unmasked_quiz_correct_answers():
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    use_case = ListOnboardingStepsForAdminUseCase(repository)

    result = await use_case.execute()

    quiz = next(s for s in result if s.id == QUIZ_STEP.id)
    assert all("correct" in q for q in quiz.config["questions"])
