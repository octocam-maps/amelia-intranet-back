"""
`GET /onboarding/admin/steps` — a diferencia de `GET /onboarding/me`, el
admin ve el catálogo COMPLETO (incluidos pasos `is_active=False`) y la
respuesta correcta del quiz sin enmascarar.

Desde el 2026-07-31 devuelve tuplas `(paso, documentos)`: la previsualización del
admin necesita los documentos o el paso 3 saldría con la lista de manuales vacía.
"""

from dataclasses import replace

import pytest

from src.features.onboarding.application.use_cases.list_onboarding_steps_admin import (
    ListOnboardingStepsForAdminUseCase,
)

from .fakes import FakeOnboardingRepository
from .steps import ALL_STEPS, MANUAL_DOCUMENTS, MANUAL_STEP, QUIZ_STEP, SIGNATURE_STEP


@pytest.mark.asyncio
async def test_admin_sees_full_catalog_including_inactive_steps():
    inactive_manual = replace(ALL_STEPS[3], is_active=False)
    steps = [ALL_STEPS[0], ALL_STEPS[1], ALL_STEPS[2], inactive_manual, ALL_STEPS[4]]
    repository = FakeOnboardingRepository(steps=steps)
    use_case = ListOnboardingStepsForAdminUseCase(repository)

    result = await use_case.execute()

    steps_only = [step for step, _ in result]
    assert [s.id for s in steps_only] == [s.id for s in ALL_STEPS]
    assert next(s for s in steps_only if s.id == inactive_manual.id).is_active is False


@pytest.mark.asyncio
async def test_admin_sees_unmasked_quiz_correct_answers():
    repository = FakeOnboardingRepository(steps=ALL_STEPS)
    use_case = ListOnboardingStepsForAdminUseCase(repository)

    result = await use_case.execute()

    quiz = next(step for step, _ in result if step.id == QUIZ_STEP.id)
    assert all("correct" in q for q in quiz.config["questions"])


@pytest.mark.asyncio
async def test_the_manual_step_ships_its_documents_for_the_preview():
    """Sin los documentos, la previsualización del paso 3 mostraría una lista de
    manuales vacía y el admin no podría revisar lo que va a leer la gente."""
    repository = FakeOnboardingRepository(steps=ALL_STEPS, documents=MANUAL_DOCUMENTS)
    use_case = ListOnboardingStepsForAdminUseCase(repository)

    result = await use_case.execute()

    documents_by_step = {step.id: documents for step, documents in result}
    manuals = documents_by_step[MANUAL_STEP.id]
    assert [d.title for d in manuals] == [
        "Manual de uso de ClickUp",
        "Manual de usuario Hincator® 2026",
    ]


@pytest.mark.asyncio
async def test_steps_without_documents_get_an_empty_list():
    """Vídeo, cuestionario y perfil se describen enteros con su `config`."""
    repository = FakeOnboardingRepository(steps=ALL_STEPS, documents=MANUAL_DOCUMENTS)
    use_case = ListOnboardingStepsForAdminUseCase(repository)

    result = await use_case.execute()

    documents_by_step = {step.id: documents for step, documents in result}
    assert documents_by_step[QUIZ_STEP.id] == []
    # La plantilla de documentación no está configurada todavía (RF-A8.4).
    assert documents_by_step[SIGNATURE_STEP.id] == []
