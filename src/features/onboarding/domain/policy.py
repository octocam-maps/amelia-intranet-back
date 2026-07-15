"""
Reglas de negocio puras del onboarding — sin SQL, sin FastAPI. Se usan desde
`application/use_cases/*` para no duplicar la ramificación por rol ni el
chequeo de "paso operable" en cada caso de uso.
"""

from datetime import datetime
from typing import Optional

from .entities import OnboardingProgress, OnboardingStep
from .errors import (
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
    if role == "externo_invitado":
        return [s for s in steps if s.type in _EXTERNAL_GUEST_ALLOWED_TYPES]
    return list(steps)


def ensure_step_allowed_for_role(step: OnboardingStep, role: str) -> None:
    """Ramificación por rol validada en el backend (regla no negociable):
    escribir el endpoint a mano no le da a un externo-invitado acceso a
    quiz/signature/profile."""
    if role == "externo_invitado" and step.type not in _EXTERNAL_GUEST_ALLOWED_TYPES:
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
