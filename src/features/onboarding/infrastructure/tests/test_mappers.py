"""
Regresión: `GET /onboarding/me` NUNCA debe devolver la respuesta correcta
del cuestionario — `_masked_config` debe quitar `correct` de cada pregunta
sin tocar el resto del `config` (umbral, texto, opciones).
"""

from src.features.onboarding.domain.entities import OnboardingProgress, OnboardingStep
from src.features.onboarding.infrastructure.mappers import (
    step_to_admin_dto,
    step_with_progress_to_dto,
)


def test_quiz_config_never_leaks_the_correct_answer():
    step = OnboardingStep(
        id="step-quiz",
        step_order=2,
        type="quiz",
        title="Cuestionario",
        config={
            "threshold": 0.7,
            "questions": [
                {"id": "q1", "text": "¿?", "options": ["a", "b"], "correct": "a"},
            ],
        },
        is_active=True,
    )
    progress = OnboardingProgress(
        id="progress-1",
        user_id="user-1",
        step_id=step.id,
        status="available",
        progress_pct=0,
        data={},
        started_at=None,
        completed_at=None,
    )

    dto = step_with_progress_to_dto(step, progress)

    assert dto.config["threshold"] == 0.7
    question = dto.config["questions"][0]
    assert question["options"] == ["a", "b"]
    assert "correct" not in question


def test_non_quiz_config_is_not_masked():
    step = OnboardingStep(
        id="step-video",
        step_order=1,
        type="video",
        title="Bienvenida",
        config={"url": "/video.mp4", "duration": 96},
        is_active=True,
    )
    progress = OnboardingProgress(
        id="progress-1",
        user_id="user-1",
        step_id=step.id,
        status="available",
        progress_pct=0,
        data={},
        started_at=None,
        completed_at=None,
    )

    dto = step_with_progress_to_dto(step, progress)

    assert dto.config == {"url": "/video.mp4", "duration": 96}


def test_admin_mapper_never_masks_the_correct_answer():
    """`GET /onboarding/admin/steps` es exclusivo del admin y a propósito
    NO enmascara — es quien edita la respuesta correcta."""
    step = OnboardingStep(
        id="step-quiz",
        step_order=2,
        type="quiz",
        title="Cuestionario",
        config={
            "threshold": 0.7,
            "questions": [
                {"id": "q1", "text": "¿?", "options": ["a", "b"], "correct": "a"},
            ],
        },
        is_active=True,
    )

    dto = step_to_admin_dto(step)

    assert dto.config["questions"][0]["correct"] == "a"
