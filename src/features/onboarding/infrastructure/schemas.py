"""DTOs de request/response (Pydantic) del feature `onboarding`."""

from datetime import date, datetime
from typing import Annotated, Any, Optional

from pydantic import BaseModel, Field, StringConstraints, field_validator


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


class UploadSignedDocumentDTO(BaseModel):
    """Resultado de `POST /steps/{step_id}/documents` (sdd/docs-firmados-
    upload-drive) — reemplaza a `SignatureDTO`. Sin hash/IP: la trazabilidad
    de "cuándo y quién" ya la guarda `employee_documents.uploaded_at`/
    `uploaded_by`; aquí solo se expone el enlace con el paso de onboarding."""

    id: str
    step_id: str
    employee_document_id: str
    uploaded_at: datetime


class AcknowledgementDTO(BaseModel):
    id: str
    step_id: str
    document_id: str
    acknowledged_at: datetime


_NON_BLANK_REQUIRED = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CompleteProfileRequestDTO(BaseModel):
    """Paso 5 del onboarding ("Completar perfil", RF §3.5) — los 6 primeros
    campos son obligatorios; `company_phone` es el único opcional ("móvil de
    empresa, si aplica"). `_NON_BLANK_REQUIRED` (`StringConstraints` con
    `strip_whitespace=True` + `min_length=1`) es la PRIMERA barrera
    anti-vacío: recorta espacios ANTES de exigir longitud, así que " " no
    cuela como si fuera un valor real (un `str` normal de Pydantic sí lo
    dejaría pasar). Deliberadamente NO se usa un `field_validator` que
    levante `ValueError` a mano: Pydantic v2 mete la excepción cruda en
    `ctx.error` del error resultante, y `JSONResponse`/`json.dumps` no sabe
    serializarla (`TypeError: Object of type ValueError is not JSON
    serializable`, reproducido en la auditoría de esta migración) — los
    errores NATIVOS de `StringConstraints` no tienen ese problema. El use
    case repite el chequeo en el dominio como SEGUNDA barrera
    (`ensure_profile_data_complete`) — no confía solo en este DTO."""

    full_name: _NON_BLANK_REQUIRED
    birth_date: date
    dni_nie: _NON_BLANK_REQUIRED
    personal_phone: _NON_BLANK_REQUIRED
    address: _NON_BLANK_REQUIRED
    department_id: _NON_BLANK_REQUIRED
    company_phone: Optional[str] = None

    @field_validator("company_phone")
    @classmethod
    def _blank_company_phone_to_none(cls, value: Optional[str]) -> Optional[str]:
        # No levanta error: un móvil de empresa vacío es válido (campo
        # opcional) — solo se normaliza " " -> `None` para no guardar
        # espacios en blanco en `user_profiles.company_phone`.
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


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
