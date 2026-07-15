"""
Reglas de negocio puras del onboarding — sin SQL, sin FastAPI. Se usan desde
`application/use_cases/*` para no duplicar la ramificación por rol ni el
chequeo de "paso operable" en cada caso de uso.
"""

from typing import Optional

from .entities import OnboardingProgress, OnboardingStep
from .errors import StepLockedError, StepNotAvailableForRoleError, StepNotOperableError

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
