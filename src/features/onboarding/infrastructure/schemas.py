"""DTOs de request/response (Pydantic) del feature `onboarding`."""

from datetime import date, datetime
from typing import Annotated, Any, Optional

from pydantic import BaseModel, Field, StringConstraints, field_validator


class OnboardingStepDocumentDTO(BaseModel):
    """Documento vigente asociado al paso (manual a leer, plantilla a firmar).

    `url` es `onboarding_documents.storage_ref`, la ÚNICA fuente de verdad de
    dónde vive el fichero. Se expone aquí para que el cliente no tenga que
    hardcodear la ruta ni duplicarla en el `config` del paso: si RRHH publica
    otra versión del manual, cambia una fila y la UI la sigue.

    `content_hash` NO se expone: es el registro de integridad interno
    (RNF2.2), no algo que el cliente necesite ni deba mostrar."""

    id: str
    kind: str
    title: str
    version: int
    url: Optional[str]
    # Cascada del paso 3 (migración 040). El cliente NO recalcula nada de esto:
    # `locked` sale de la misma regla de dominio que valida el POST
    # (`ensure_manual_unlocked`), así que el candado que pinta y el 422 que
    # recibiría si insistiera no pueden discrepar.
    display_order: int = 1
    acknowledged: bool = False
    locked: bool = False


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
    # Documentos del paso, en orden de lectura. LISTA desde la migración 040: el
    # paso `manual` admite varios en cascada. Vacía en vídeo, cuestionario y
    # perfil, y también si RRHH todavía no ha configurado ninguno.
    documents: list[OnboardingStepDocumentDTO] = []
    # DEPRECADO — se mantiene por compatibilidad con clientes anteriores a la
    # 040, que leen `step.document`. Es el PRIMER documento de `documents`
    # (para el paso 3, el manual que abre la cascada). Retirar cuando no queden
    # clientes viejos desplegados.
    document: Optional[OnboardingStepDocumentDTO] = None


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
    # Preguntas falladas, por ID y en el orden del cuestionario. IDS, NUNCA la
    # respuesta correcta: el cliente ya tiene los enunciados (el `GET
    # /onboarding/me` manda `questions` con `correct` enmascarado), así que con
    # el id puede señalar qué falló sin que el backend filtre la solución.
    # Importa especialmente porque hay un segundo intento: revelar la correcta
    # tras el primero lo convertiría en un trámite. Vacía si se aprobó.
    incorrect_question_ids: list[str] = []
    # Para que la UI diga "te queda 1 intento" en vez de dejarlo a la
    # adivinanza. `attempts_left` ya descuenta el envío actual y vale 0 si se
    # aprobó (el paso queda `completed` y no admite más envíos).
    attempts_used: int = 1
    attempts_left: int = 0


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
    # Documentos del paso, para la PREVISUALIZACIÓN del admin. Sin `acknowledged`
    # ni `locked`: la cascada es el estado de UN trabajador concreto, y en una
    # previsualización no hay trabajador — pintar candados aquí sugeriría que el
    # admin tiene un progreso que no tiene.
    documents: list[OnboardingStepDocumentDTO] = []


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


class EmployeeStepProgressDTO(BaseModel):
    """Un paso concreto de una persona, para el desglose de la bandeja de
    administración."""

    step_order: int
    title: str
    status: str  # locked | available | in_progress | completed


class EmployeeOnboardingSummaryDTO(BaseModel):
    user_id: str
    full_name: str
    email: str
    avatar_url: Optional[str]
    status: str
    completed_steps: int
    total_steps: int
    current_step_title: Optional[str]
    # Desglose paso a paso, para que el admin vea DÓNDE está atascada una persona
    # y no solo "3 de 5". Vacío si nunca visitó su onboarding — que es distinto de
    # tener los 5 pasos bloqueados.
    steps: list[EmployeeStepProgressDTO] = []


class OnboardingProgressOverviewDTO(BaseModel):
    employees: list[EmployeeOnboardingSummaryDTO]


class AcknowledgeManualDTO(BaseModel):
    """Body de `POST /steps/{step_id}/acknowledge`.

    `document_id` es opcional a propósito: un cliente anterior a la migración 040
    confirmaba "el manual" sin decir cuál, y con un solo manual eso no era
    ambiguo. Ausente = "el siguiente pendiente de la cascada", que es lo único
    que podía significar entonces."""

    document_id: Optional[str] = None
