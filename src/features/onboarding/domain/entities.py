"""Entidades de dominio del feature `onboarding`. Sin dependencias de framework/SQL."""

from dataclasses import dataclass, field
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
    """Un intento de cuestionario. Se admiten hasta
    `policy.MAX_QUIZ_ATTEMPTS` (2 desde 2026-07-29); `attempt_number` los
    numera y su `UNIQUE(user_id, step_id, attempt_number)` en
    `onboarding_quiz_attempts` es la garantía real a nivel de BD contra la
    carrera de doble clic — sustituye a la vieja `UNIQUE(user_id, step_id)`,
    que era la que imponía el intento único."""

    id: str
    user_id: str
    step_id: str
    answers: dict[str, Any]
    score: float
    passed: bool
    submitted_at: datetime
    attempt_number: int = 1


@dataclass(frozen=True)
class QuizSubmissionResult:
    """Lo que el trabajador necesita ver tras enviar el cuestionario, que es
    más que el intento en sí: QUÉ preguntas falló y CUÁNTOS intentos le quedan.

    `incorrect_question_ids` son ids, no respuestas correctas — el cliente ya
    tiene los enunciados y con el id puede señalar el fallo sin que el backend
    filtre la solución (ver `policy.incorrect_question_ids`)."""

    attempt: QuizAttempt
    incorrect_question_ids: list[str]
    attempts_used: int
    attempts_left: int


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
    # Orden de lectura dentro de su `kind` (migración 040). Para los manuales
    # define la CASCADA del paso 3: no se confirma uno sin los de orden menor.
    # Default a propósito, para no romper los tests y fakes que construyen
    # documentos sin orden — ahí el orden no es lo que se está probando.
    display_order: int = 1
    # `True` = hay que confirmar su lectura para completar el paso 3 (entra en la
    # cascada). `False` = solo está en la biblioteca de consulta (migración 043).
    #
    # La biblioteca es un SUPERCONJUNTO del paso: el manual de uso de la intranet
    # se consulta pero no se exige leer, y meterlo en la cascada habría alargado el
    # onboarding con un manual que nadie pidió.
    requires_acknowledgement: bool = True


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
    # Desglose paso a paso, para que el admin pueda ver DÓNDE está atascada una
    # persona y no solo "3 de 5". El dato ya venía en el snapshot: antes se
    # colapsaba al agregar y se tiraba.
    #
    # Vacío si el usuario nunca ha visitado su onboarding (progreso sin
    # inicializar), que es distinto de "tiene 5 pasos bloqueados".
    steps: list[StepProgressSnapshot] = field(default_factory=list)


@dataclass(frozen=True)
class StepDocument:
    """Un documento del paso junto a su estado EN LA CASCADA para este usuario
    (migración 040).

    Existe para que `acknowledged`/`locked` los calcule el DOMINIO
    (`resolve_step_documents` en `policy.py`) y no el mapper: son la misma regla
    que valida el POST de confirmación, así que el candado que pinta la UI y el
    422 que recibiría si insistiera salen de un solo sitio y no pueden
    discrepar."""

    document: OnboardingDocument
    acknowledged: bool
    # `True` = hay un documento anterior en la cascada sin confirmar. Solo puede
    # ser `True` en los manuales: el `signature` es uno solo.
    locked: bool
