from typing import Any

from ..domain.entities import (
    DocumentAcknowledgement,
    DocumentSignature,
    OnboardingProgress,
    OnboardingStep,
    QuizAttempt,
)
from .schemas import (
    AcknowledgementDTO,
    OnboardingMeDTO,
    OnboardingProgressDTO,
    OnboardingStepDTO,
    QuizResultDTO,
    SignatureDTO,
)


def _masked_config(step: OnboardingStep) -> dict[str, Any]:
    """El `GET /onboarding/me` NUNCA devuelve la respuesta correcta del
    cuestionario — se quita `correct` de cada pregunta antes de mapear a
    DTO. El resto del `config` (umbral, texto, opciones) sí se expone."""
    if step.type != "quiz":
        return step.config

    questions = step.config.get("questions", [])
    masked_questions = [
        {key: value for key, value in question.items() if key != "correct"}
        for question in questions
    ]
    return {**step.config, "questions": masked_questions}


def step_with_progress_to_dto(
    step: OnboardingStep, progress: OnboardingProgress
) -> OnboardingStepDTO:
    return OnboardingStepDTO(
        id=step.id,
        step_order=step.step_order,
        type=step.type,
        title=step.title,
        config=_masked_config(step),
        status=progress.status,
        progress_pct=progress.progress_pct,
        data=progress.data,
        started_at=progress.started_at,
        completed_at=progress.completed_at,
    )


def steps_with_progress_to_dto(
    pairs: list[tuple[OnboardingStep, OnboardingProgress]],
) -> OnboardingMeDTO:
    return OnboardingMeDTO(
        steps=[step_with_progress_to_dto(step, progress) for step, progress in pairs]
    )


def progress_to_dto(progress: OnboardingProgress) -> OnboardingProgressDTO:
    return OnboardingProgressDTO(
        id=progress.id,
        step_id=progress.step_id,
        status=progress.status,
        progress_pct=progress.progress_pct,
        started_at=progress.started_at,
        completed_at=progress.completed_at,
    )


def quiz_attempt_to_dto(attempt: QuizAttempt) -> QuizResultDTO:
    return QuizResultDTO(
        step_id=attempt.step_id,
        score=attempt.score,
        passed=attempt.passed,
        submitted_at=attempt.submitted_at,
    )


def signature_to_dto(signature: DocumentSignature, step_id: str) -> SignatureDTO:
    return SignatureDTO(
        id=signature.id,
        step_id=step_id,
        document_id=signature.document_id,
        document_version=signature.document_version,
        signed_at=signature.signed_at,
    )


def acknowledgement_to_dto(
    acknowledgement: DocumentAcknowledgement, step_id: str
) -> AcknowledgementDTO:
    return AcknowledgementDTO(
        id=acknowledgement.id,
        step_id=step_id,
        document_id=acknowledgement.document_id,
        acknowledged_at=acknowledgement.acknowledged_at,
    )
