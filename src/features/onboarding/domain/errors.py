from src.shared.errors.base import (
    InsufficientPermissionsError,
    NotFoundError,
    ValidationError,
)


class OnboardingStepNotFoundError(NotFoundError):
    """No existe un paso de onboarding con ese id."""


class OnboardingDocumentNotFoundError(NotFoundError):
    """No hay un documento activo del `kind` requerido (signature/manual) —
    el admin todavía no lo ha configurado (Fase 5)."""


class WrongStepTypeError(ValidationError):
    """El endpoint invocado no corresponde al `type` de este paso (p.ej.
    reportar `video-progress` sobre un paso `quiz`)."""


class StepNotAvailableForRoleError(InsufficientPermissionsError):
    """El rol del usuario no tiene este paso en su onboarding — el
    externo-invitado solo hace vídeo + manual (docs/permisos-roles.md §
    Onboarding: "parcial, sin firma/cuestionario/perfil"). Escribir el
    endpoint a mano no lo salta: se rechaza aquí, en el backend."""


class StepLockedError(ValidationError):
    """El paso anterior (por `step_order`) no está `completed` — no se
    puede operar sobre este paso todavía. Bloqueo secuencial validado en el
    backend, no solo en la UI."""


class StepNotOperableError(ValidationError):
    """El paso no está en un estado que admita esta operación: ya está
    `completed` (no se puede repetir) o su progreso no se ha inicializado
    todavía (el cliente no llamó a `GET /onboarding/me` primero)."""


class InvalidVideoProgressError(ValidationError):
    """El progreso de vídeo reportado no es monotónico creciente o el salto
    es irrealista (p.ej. de 0 a 100 de golpe) — indicio de intento de saltar
    el vídeo sin verlo (Opción A del requerimiento: "no-skip")."""


class QuizAlreadyAttemptedError(ValidationError):
    """Ya existe un intento de este cuestionario para este usuario — un
    único intento, garantizado por `UNIQUE(user_id, step_id)` en
    `onboarding_quiz_attempts`."""


class InvalidStepConfigError(ValidationError):
    """El `config` (JSONB) enviado por el admin no es coherente con el
    `type` del paso — p.ej. un quiz sin `questions`/`threshold`, o una
    pregunta sin `correct` entre sus `options`. Se valida en el backend
    porque `config` es data-driven (JSONB, no tipado por columna)."""


class OnboardingProgressNotFoundError(NotFoundError):
    """El usuario no tiene una fila de progreso inicializada para este
    paso (nunca llamó a `GET /onboarding/me`) — no hay nada que reabrir."""
