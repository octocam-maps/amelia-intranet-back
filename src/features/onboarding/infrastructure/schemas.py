"""DTOs de request/response (Pydantic) del feature `onboarding`."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class OnboardingStepDTO(BaseModel):
    id: str
    step_order: int
    type: str
    title: str
    # Enmascarado por el mapper cuando `type == "quiz"` — nunca incluye el
    # campo `correct` de cada pregunta (regla no negociable: la corrección
    # es server-side).
    config: dict[str, Any]
    status: str
    progress_pct: int
    data: dict[str, Any]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class OnboardingMeDTO(BaseModel):
    steps: list[OnboardingStepDTO]


class VideoProgressRequestDTO(BaseModel):
    progress_pct: int = Field(ge=0, le=100)


class OnboardingProgressDTO(BaseModel):
    id: str
    step_id: str
    status: str
    progress_pct: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class QuizSubmitRequestDTO(BaseModel):
    # `question_id -> respuesta elegida` (mismo valor que el string de
    # `options`, no un índice) — ver shape completo en
    # `020_onboarding_steps_seed.sql`.
    answers: dict[str, str]


class QuizResultDTO(BaseModel):
    step_id: str
    score: float
    passed: bool
    submitted_at: datetime


class SignatureDTO(BaseModel):
    id: str
    step_id: str
    document_id: str
    document_version: int
    signed_at: datetime


class AcknowledgementDTO(BaseModel):
    id: str
    step_id: str
    document_id: str
    acknowledged_at: datetime


class CompleteProfileRequestDTO(BaseModel):
    # Borrador: el esquema real del perfil (Fase 3) todavía no está
    # diseñado — se acepta un payload básico de campos opcionales y se
    # guarda tal cual en `onboarding_progress.data`.
    phone: Optional[str] = None
    address: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None


class AdminStepDTO(BaseModel):
    """A diferencia de `OnboardingStepDTO`, `config` NUNCA se enmascara
    aquí — el admin edita la respuesta correcta del quiz."""

    id: str
    step_order: int
    type: str
    title: str
    config: dict[str, Any]
    is_active: bool


class AdminStepListDTO(BaseModel):
    steps: list[AdminStepDTO]


class UpdateOnboardingStepRequestDTO(BaseModel):
    title: Optional[str] = None
    is_active: Optional[bool] = None
    # Reemplazo COMPLETO del JSONB del paso (no merge profundo) — el admin
    # envía la config entera resultante de editar el formulario.
    config: Optional[dict[str, Any]] = None


class ResetQuizRequestDTO(BaseModel):
    user_id: str


class EmployeeOnboardingSummaryDTO(BaseModel):
    user_id: str
    full_name: str
    email: str
    avatar_url: Optional[str]
    status: str
    completed_steps: int
    total_steps: int
    current_step_title: Optional[str]


class OnboardingProgressOverviewDTO(BaseModel):
    employees: list[EmployeeOnboardingSummaryDTO]
