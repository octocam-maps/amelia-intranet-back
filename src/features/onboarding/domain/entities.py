"""Entidades de dominio del feature `onboarding`. Sin dependencias de framework/SQL."""

from dataclasses import dataclass
from datetime import datetime
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
class DocumentSignature:
    """Firma digital trazable (paso 3): fecha/hora (`signed_at`), IP
    (`ip_address`) y hash del documento firmado (`document_hash`, congelado
    en el momento de la firma) — regla no negociable del requerimiento §7.
    `document_id`/`user_id` en la BD usan `ON DELETE RESTRICT`: una firma
    nunca se borra en cascada."""

    id: str
    user_id: str
    document_id: str
    document_version: int
    document_hash: str
    signature_hash: str
    signed_at: datetime
    ip_address: str
    user_agent: Optional[str]


@dataclass(frozen=True)
class DocumentAcknowledgement:
    """Confirmación explícita de lectura de un manual (paso 4). Menos
    exigente que la firma — sin `signature_hash`, la IP es informativa."""

    id: str
    user_id: str
    document_id: str
    acknowledged_at: datetime
    ip_address: Optional[str]
