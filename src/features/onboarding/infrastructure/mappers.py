from typing import Any, Optional

from ..domain.entities import (
    DocumentAcknowledgement,
    EmployeeOnboardingSummary,
    OnboardingDocumentUpload,
    OnboardingProgress,
    OnboardingStep,
    QuizSubmissionResult,
    StepDocument,
)
from .schemas import (
    AcknowledgementDTO,
    AdminStepDTO,
    AdminStepListDTO,
    EmployeeOnboardingSummaryDTO,
    OnboardingMeDTO,
    OnboardingProgressDTO,
    OnboardingProgressOverviewDTO,
    OnboardingStepDTO,
    OnboardingStepDocumentDTO,
    QuizResultDTO,
    UploadSignedDocumentDTO,
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
    step: OnboardingStep,
    progress: OnboardingProgress,
    documents: Optional[list[StepDocument]] = None,
) -> OnboardingStepDTO:
    step_documents = documents or []
    document_dtos = [
        OnboardingStepDocumentDTO(
            id=item.document.id,
            kind=item.document.kind,
            title=item.document.title,
            version=item.document.version,
            url=item.document.storage_ref,
            display_order=item.document.display_order,
            acknowledged=item.acknowledged,
            locked=item.locked,
        )
        for item in step_documents
    ]
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
        documents=document_dtos,
        # DEPRECADO, por compatibilidad con clientes anteriores a la 040: el
        # PRIMERO de la cascada, que es el manual que abre el paso 3.
        document=document_dtos[0] if document_dtos else None,
    )


def steps_with_progress_to_dto(
    triples: list[
        tuple[OnboardingStep, OnboardingProgress, list[StepDocument]]
    ],
) -> OnboardingMeDTO:
    return OnboardingMeDTO(
        steps=[
            step_with_progress_to_dto(step, progress, documents)
            for step, progress, documents in triples
        ]
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


def quiz_submission_to_dto(result: QuizSubmissionResult) -> QuizResultDTO:
    return QuizResultDTO(
        step_id=result.attempt.step_id,
        score=result.attempt.score,
        passed=result.attempt.passed,
        submitted_at=result.attempt.submitted_at,
        incorrect_question_ids=result.incorrect_question_ids,
        attempts_used=result.attempts_used,
        attempts_left=result.attempts_left,
    )


def document_upload_to_dto(
    upload: OnboardingDocumentUpload, step_id: str
) -> UploadSignedDocumentDTO:
    return UploadSignedDocumentDTO(
        id=upload.id,
        step_id=step_id,
        employee_document_id=upload.employee_document_id,
        uploaded_at=upload.uploaded_at,
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


def step_to_admin_dto(step: OnboardingStep) -> AdminStepDTO:
    """A diferencia de `step_with_progress_to_dto`, NUNCA enmascara
    `config` — el admin es quien edita la respuesta correcta del quiz."""
    return AdminStepDTO(
        id=step.id,
        step_order=step.step_order,
        type=step.type,
        title=step.title,
        config=step.config,
        is_active=step.is_active,
    )


def steps_to_admin_dto(steps: list[OnboardingStep]) -> AdminStepListDTO:
    return AdminStepListDTO(steps=[step_to_admin_dto(step) for step in steps])


def employee_summary_to_dto(
    summary: EmployeeOnboardingSummary,
) -> EmployeeOnboardingSummaryDTO:
    return EmployeeOnboardingSummaryDTO(
        user_id=summary.user_id,
        full_name=summary.full_name,
        email=summary.email,
        avatar_url=summary.avatar_url,
        status=summary.status,
        completed_steps=summary.completed_steps,
        total_steps=summary.total_steps,
        current_step_title=summary.current_step_title,
    )


def progress_overview_to_dto(
    summaries: list[EmployeeOnboardingSummary],
) -> OnboardingProgressOverviewDTO:
    return OnboardingProgressOverviewDTO(
        employees=[employee_summary_to_dto(summary) for summary in summaries]
    )
