"""
Reglas de negocio puras del onboarding — sin SQL, sin FastAPI. Se usan desde
`application/use_cases/*` para no duplicar la ramificación por rol ni el
chequeo de "paso operable" en cada caso de uso.
"""

import re
from datetime import date, datetime
from typing import Optional

from typing import Any

from src.shared.auth.roles import RoleCode

from .entities import (
    EmployeeOnboardingSnapshot,
    EmployeeOnboardingSummary,
    OnboardingProgress,
    OnboardingStep,
    ProfileCompletionData,
)
from .errors import (
    IncompleteProfileDataError,
    InvalidStepConfigError,
    InvalidVideoProgressError,
    StepLockedError,
    StepNotAvailableForRoleError,
    StepNotOperableError,
)

# El externo-invitado hace onboarding PARCIAL: solo vídeo + manual
# (docs/permisos-roles.md § Onboarding: "parcial, sin firma/cuestionario/perfil").
# administrador y empleado hacen los 5 pasos completos.
_EXTERNAL_GUEST_ALLOWED_TYPES = frozenset({"video", "manual"})

# Salto máximo (en puntos de `progress_pct`) que se admite entre dos reportes
# consecutivos del vídeo del paso 1. Cualquier salto mayor —incluido el caso
# explícito del requerimiento, 0 -> 100 de golpe— se rechaza como intento de
# saltar el vídeo sin verlo (Opción A: "no-skip"). El valor es una política de
# producto, no una medición exacta del reproductor: asumimos reportes de
# progreso frecuentes (cada pocos segundos de un vídeo corto) y dejamos
# margen para picos de red, sin permitir terminar el vídeo en un único salto.
MAX_VIDEO_PROGRESS_JUMP_PCT = 30

# Margen (en puntos de `progress_pct`) que se admite POR ENCIMA de lo que el
# tiempo real transcurrido justificaría, para absorber picos de red/buffer
# del reproductor y el desfase entre el evento de "play" y el primer
# `POST /video-progress`. Es deliberadamente generoso (no una medición
# exacta del reproductor) para no reventar de falsos positivos con una
# conexión lenta — pero acota el bypass real: 4 requests sin esperar
# (0->29->58->87->100) violan el % de salto máximo por request o, si se
# reparten en llamadas más pequeñas, violan este techo por tiempo real,
# porque entre request y request casi no pasa tiempo de reloj.
VIDEO_PROGRESS_TIME_MARGIN_PCT = 20


def steps_applicable_to_role(
    steps: list[OnboardingStep], role: str
) -> list[OnboardingStep]:
    """Filtra el catálogo de pasos a los que el rol tiene derecho. El GET
    /onboarding/me y la inicialización de progreso SOLO consideran estos
    pasos — el externo-invitado ni siquiera llega a tener una fila de
    progreso para quiz/signature/profile."""
    if role == RoleCode.EXTERNO_INVITADO:
        return [s for s in steps if s.type in _EXTERNAL_GUEST_ALLOWED_TYPES]
    return list(steps)


def ensure_step_allowed_for_role(step: OnboardingStep, role: str) -> None:
    """Ramificación por rol validada en el backend (regla no negociable):
    escribir el endpoint a mano no le da a un externo-invitado acceso a
    quiz/signature/profile."""
    if role == RoleCode.EXTERNO_INVITADO and step.type not in _EXTERNAL_GUEST_ALLOWED_TYPES:
        raise StepNotAvailableForRoleError(
            "Tu invitación no incluye este paso del onboarding."
        )


def ensure_step_operable(progress: Optional[OnboardingProgress]) -> OnboardingProgress:
    """Un paso solo admite operaciones (reportar progreso, firmar, confirmar
    lectura, completar perfil) si su progreso está en `available` o
    `in_progress`. `locked` -> bloqueo secuencial; `completed` -> ya no se
    repite (el cuestionario en particular es de un único intento)."""
    if progress is None or progress.status == "locked":
        raise StepLockedError(
            "Este paso todavía está bloqueado — completa primero el paso anterior."
        )
    if progress.status == "completed":
        raise StepNotOperableError("Este paso ya está completado.")
    return progress


def ensure_video_progress_matches_elapsed_time(
    *,
    progress: OnboardingProgress,
    step: OnboardingStep,
    new_pct: int,
    now: datetime,
) -> None:
    """Valida el `new_pct` reportado contra el TIEMPO REAL transcurrido desde
    `progress.started_at` — el chequeo de salto máximo por request
    (`MAX_VIDEO_PROGRESS_JUMP_PCT`) por sí solo no evita el bypass real: 4
    requests rápidas y consecutivas (0->29->58->87->100), cada una dentro del
    30% permitido, completan el vídeo sin haberlo visto.

    `progress.started_at is None` significa que este es el PRIMER reporte de
    progreso de este usuario para este paso — todavía no hay una base
    temporal contra la que medir, así que aquí no se valida nada (solo aplica
    el chequeo de salto de `ensure_step_operable`/`MAX_VIDEO_PROGRESS_JUMP_PCT`
    en el use case). El propio UPDATE del repositorio es quien fija
    `started_at` en ese primer reporte.

    Si el paso no trae `duration` en su `config` (no debería pasar para
    `type=video`, pero `config` es JSONB data-driven y no lo garantiza el
    tipo), no se puede calcular el techo — se deja pasar sin validar en vez
    de romper el flujo por un dato de catálogo mal cargado.
    """
    if progress.started_at is None:
        return

    duration_seconds = step.config.get("duration")
    if not duration_seconds:
        return

    elapsed_seconds = (now - progress.started_at).total_seconds()
    allowed_pct = (elapsed_seconds / duration_seconds) * 100 + VIDEO_PROGRESS_TIME_MARGIN_PCT
    if new_pct > allowed_pct:
        raise InvalidVideoProgressError(
            "El progreso reportado va por delante del tiempo real de "
            "reproducción — el vídeo no se puede saltar."
        )


def validate_step_config(step_type: str, config: dict[str, Any]) -> None:
    """Valida coherencia mínima del `config` (JSONB) que el admin edita vía
    `PATCH /onboarding/admin/steps/{id}` — data-driven por `type`, así que
    no hay columna/constraint de BD que lo garantice; se valida aquí antes
    de persistir. Los tipos sin shape obligatorio (`signature`, `manual`,
    `profile`) no se validan: su `config` hoy no se usa para nada crítico."""
    if step_type == "quiz":
        _validate_quiz_config(config)
    elif step_type == "video":
        _validate_video_config(config)


def _validate_quiz_config(config: dict[str, Any]) -> None:
    questions = config.get("questions")
    if not isinstance(questions, list) or not questions:
        raise InvalidStepConfigError(
            "El cuestionario necesita al menos una pregunta en `questions`."
        )

    for question in questions:
        if not isinstance(question, dict):
            raise InvalidStepConfigError("Cada pregunta debe ser un objeto.")

        missing = [
            key for key in ("id", "text", "options", "correct") if key not in question
        ]
        if missing:
            raise InvalidStepConfigError(
                f"Falta el campo {', '.join(missing)} en una pregunta del cuestionario."
            )

        options = question["options"]
        if not isinstance(options, list) or not options:
            raise InvalidStepConfigError(
                "Cada pregunta necesita al menos una opción en `options`."
            )
        if question["correct"] not in options:
            raise InvalidStepConfigError(
                "La respuesta correcta (`correct`) debe ser una de las `options`."
            )

    threshold = config.get("threshold")
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        raise InvalidStepConfigError(
            "El cuestionario necesita un `threshold` numérico entre 0 y 1."
        )
    if not (0 <= threshold <= 1):
        raise InvalidStepConfigError("El `threshold` debe estar entre 0 y 1.")


def _validate_video_config(config: dict[str, Any]) -> None:
    url = config.get("url")
    if not isinstance(url, str) or not url:
        raise InvalidStepConfigError("El vídeo necesita una `url` no vacía.")

    duration = config.get("duration")
    if (
        not isinstance(duration, (int, float))
        or isinstance(duration, bool)
        or duration <= 0
    ):
        raise InvalidStepConfigError(
            "El vídeo necesita una `duration` numérica positiva (segundos)."
        )


# DNI: 8 dígitos + letra. NIE: X/Y/Z + 7 dígitos + letra. Valida solo el
# FORMATO (no la letra de control real, que requiere el algoritmo módulo 23
# del BOE) — decisión deliberada: el requerimiento (RF §3.5) solo pide "sin
# campos vacíos", no una validación notarial del documento, y el proyecto no
# tiene hoy un helper de letra de control. Si en el futuro se necesita
# verificar la letra, este es el único punto a tocar.
_DNI_NIE_PATTERN = re.compile(r"^(\d{8}[A-Za-z]|[XYZxyz]\d{7}[A-Za-z])$")

# Los 6 campos de texto obligatorios del paso 5 (RF §3.5) — `company_phone`
# es el único opcional ("si aplica") y por eso no está en esta lista.
_REQUIRED_PROFILE_TEXT_FIELDS = (
    "full_name",
    "dni_nie",
    "personal_phone",
    "address",
    "department_id",
)


def ensure_profile_data_complete(profile: ProfileCompletionData) -> None:
    """Anti-vacío server-side del paso 5 ("Completar perfil", RF §3.5):
    rechaza cualquier campo obligatorio ausente, vacío o de solo espacios —
    un `str` de Pydantic no basta por sí solo, y este chequeo es la SEGUNDA
    barrera (además del DTO) para que el use case no dependa únicamente de
    la validación HTTP. "Ocultar ≠ proteger": esto es lo que de verdad
    bloquea el paso, no el formulario del frontend."""
    missing = [
        field
        for field in _REQUIRED_PROFILE_TEXT_FIELDS
        if not str(getattr(profile, field) or "").strip()
    ]
    if missing:
        raise IncompleteProfileDataError(
            "Faltan campos obligatorios del perfil: " + ", ".join(missing) + "."
        )

    if profile.birth_date is None:
        raise IncompleteProfileDataError(
            "La fecha de nacimiento es obligatoria."
        )
    if profile.birth_date >= date.today():
        raise IncompleteProfileDataError(
            "La fecha de nacimiento no es válida."
        )

    if not _DNI_NIE_PATTERN.match(profile.dni_nie.strip()):
        raise IncompleteProfileDataError(
            "El DNI/NIE no tiene un formato válido "
            "(8 dígitos + letra, o X/Y/Z + 7 dígitos + letra)."
        )


# Estados de progreso que cuentan como "todavía sin empezar" a efectos del
# panel de admin — sin filas de progreso (nunca inicializado) o con todas
# sus filas en `locked` (inicializado pero sin tocar ningún paso).
_NOT_STARTED_STATUSES = frozenset({"locked"})
_OPERABLE_STATUSES = frozenset({"available", "in_progress"})


def summarize_employee_onboarding(
    snapshot: EmployeeOnboardingSnapshot, *, total_steps: int
) -> EmployeeOnboardingSummary:
    """Resume el progreso de un empleado para `GET /onboarding/admin/progress`
    — pura lógica de negocio sobre las filas ya unidas por el repositorio
    (`domain` no toca SQL). `total_steps` viene de
    `steps_applicable_to_role` sobre el catálogo — así el externo-invitado
    (onboarding parcial) no aparece eternamente `in_progress` por comparar
    contra los 5 pasos completos."""
    completed_steps = sum(1 for s in snapshot.steps if s.status == "completed")

    not_started = not snapshot.steps or all(
        s.status in _NOT_STARTED_STATUSES for s in snapshot.steps
    )

    if not_started:
        status = "not_started"
    elif completed_steps >= total_steps:
        status = "completed"
    else:
        status = "in_progress"

    current_step = next(
        (
            s
            for s in sorted(snapshot.steps, key=lambda s: s.step_order)
            if s.status in _OPERABLE_STATUSES
        ),
        None,
    )

    return EmployeeOnboardingSummary(
        user_id=snapshot.user_id,
        full_name=snapshot.full_name,
        email=snapshot.email,
        avatar_url=snapshot.avatar_url,
        status=status,
        completed_steps=completed_steps,
        total_steps=total_steps,
        current_step_title=current_step.title if current_step else None,
    )
