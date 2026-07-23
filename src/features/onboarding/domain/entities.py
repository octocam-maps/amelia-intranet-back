"""Entidades de dominio del feature `onboarding`. Sin dependencias de framework/SQL."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional


@dataclass(frozen=True)
class OnboardingStep:
    """Catálogo de pasos (configurable por admin, Fase 5) — ver
    `002_onboarding.sql` y el seed `020_onboarding_steps_seed.sql` para los 5
    pasos sembrados. `config` es data-driven por `type`: vídeo -> {url,
    duration}; quiz -> {threshold, questions:[{id,text,options,correct}]}."""

    id: str
    step_order: int
    type: str  # video | quiz | signature | manual | profile
    title: str
    config: dict[str, Any]
    is_active: bool


@dataclass(frozen=True)
class OnboardingProgress:
    """Progreso de UN usuario en UN paso. El backend calcula el desbloqueo:
    un paso solo pasa a `available` si el anterior (por `step_order`) está
    `completed` — ver `IOnboardingRepository.unlock_next_step`."""

    id: str
    user_id: str
    step_id: str
    status: str  # locked | available | in_progress | completed
    progress_pct: int
    data: dict[str, Any]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


@dataclass(frozen=True)
class QuizAttempt:
    """Intento de cuestionario — ÚNICO por `UNIQUE(user_id, step_id)` en
    `onboarding_quiz_attempts` (garantía real a nivel de BD, no solo en la
    app)."""

    id: str
    user_id: str
    step_id: str
    answers: dict[str, Any]
    score: float
    passed: bool
    submitted_at: datetime


@dataclass(frozen=True)
class OnboardingDocument:
    """Documento corporativo versionado (firmar o leer/confirmar).
    `content_hash` es el SHA-256 del contenido vigente — lo que se "congela"
    en la firma para que sea verificable después de que el documento cambie
    de versión."""

    id: str
    kind: str  # signature | manual
    title: str
    version: int
    content_hash: str
    storage_ref: Optional[str]
    is_active: bool


@dataclass(frozen=True)
class OnboardingDocumentUpload:
    """Enlace "este documento firmado subido satisfizo el paso 3 de
    onboarding de ESTE usuario" (`onboarding_document_uploads`) —
    distingue esto de un documento `category='signed'` que un admin subiera
    suelto vía `POST /documents` fuera del flujo de onboarding.
    `onboarding_document_id`/`employee_document_id` usan `ON DELETE
    RESTRICT` en la BD: el enlace nunca se borra en cascada."""

    id: str
    user_id: str
    onboarding_document_id: str
    employee_document_id: str
    uploaded_at: datetime


@dataclass(frozen=True)
class DocumentAcknowledgement:
    """Confirmación explícita de lectura de un manual (paso 4). Menos
    exigente que la firma — sin `signature_hash`, la IP es informativa."""

    id: str
    user_id: str
    document_id: str
    acknowledged_at: datetime
    ip_address: Optional[str]


@dataclass(frozen=True)
class StepProgressSnapshot:
    """Progreso de UN usuario en UN paso, tal como lo necesita el panel de
    administración (Fase 5): solo lo mínimo para calcular `status` y
    `current_step_title` sin volver a tocar la BD — ver
    `summarize_employee_onboarding` en `domain/policy.py`."""

    step_order: int
    title: str
    status: str  # locked | available | in_progress | completed


@dataclass(frozen=True)
class EmployeeOnboardingSnapshot:
    """Un empleado (o externo-invitado) con SUS filas de progreso ya unidas
    a su paso — puede venir con `steps=[]` si todavía no visitó `GET
    /onboarding/me` ni una vez (no inicializado)."""

    user_id: str
    full_name: str
    email: str
    avatar_url: Optional[str]
    role: str
    steps: list[StepProgressSnapshot]


@dataclass(frozen=True)
class ProfileCompletionData:
    """Payload tipado del paso 5 (`profile`, "Completar perfil" — RF §3.5).
    Value object de dominio puro: sin Pydantic ni SQL. Los 6 primeros campos
    son obligatorios; `company_phone` es el único opcional ("móvil de
    empresa, si aplica"). La validación anti-vacío/formato vive en
    `domain.policy.ensure_profile_data_complete` — un `str` por sí solo no
    basta porque no rechaza un valor de solo espacios ni un `None` llegado
    por otra vía que no sea el DTO de FastAPI (defensa en profundidad, igual
    criterio que el resto de reglas "no negociables" del requerimiento)."""

    full_name: str
    birth_date: Optional[date]
    dni_nie: str
    personal_phone: str
    address: str
    department_id: str
    company_phone: Optional[str] = None


@dataclass(frozen=True)
class EmployeeOnboardingSummary:
    """Fila lista para `GET /onboarding/admin/progress` — ya resuelta por
    `summarize_employee_onboarding` (domain, sin SQL)."""

    user_id: str
    full_name: str
    email: str
    avatar_url: Optional[str]
    status: str  # not_started | in_progress | completed
    completed_steps: int
    total_steps: int
    current_step_title: Optional[str]
