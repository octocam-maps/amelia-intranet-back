"""
Puertos (Protocols) del feature `onboarding`. `domain` no importa nada de
`infrastructure` ni de FastAPI — la implementación concreta (asyncpg) vive
en `infrastructure` y se inyecta aquí por duck typing estructural.
"""

from datetime import datetime
from typing import Any, Optional, Protocol

from .entities import (
    DocumentAcknowledgement,
    DocumentSignature,
    OnboardingDocument,
    OnboardingProgress,
    OnboardingStep,
    QuizAttempt,
)


class IOnboardingRepository(Protocol):
    async def list_active_steps(self) -> list[OnboardingStep]:
        """Catálogo completo (los 5 pasos), ordenado por `step_order`."""
        ...

    async def find_step_by_id(self, step_id: str) -> Optional[OnboardingStep]: ...

    async def list_progress_for_user(
        self, user_id: str
    ) -> list[OnboardingProgress]: ...

    async def find_progress(
        self, user_id: str, step_id: str
    ) -> Optional[OnboardingProgress]: ...

    async def ensure_progress_initialized(
        self, user_id: str, steps_in_order: list[OnboardingStep]
    ) -> None:
        """Inserta la fila de progreso que falte para cada paso aplicable al
        rol: el primero (por `step_order`) nace `available`, el resto
        `locked`. Idempotente (`ON CONFLICT DO NOTHING`) — se puede llamar en
        cada `GET /onboarding/me` sin duplicar filas."""
        ...

    async def update_video_progress(
        self, user_id: str, step_id: str, *, new_pct: int
    ) -> Optional[OnboardingProgress]:
        """UPDATE atómico condicionado a `status IN ('available',
        'in_progress')` — `None` si el paso no está en un estado operable
        (bloqueo/ya completado). La validación de monotonía/salto vive en el
        use case (lee el progreso actual antes de llamar); aquí solo se
        aplica el nuevo valor y se decide `in_progress`/`completed`."""
        ...

    async def unlock_next_step(self, user_id: str, completed_step_order: int) -> None:
        """Desbloquea el paso `locked` con el `step_order` inmediatamente
        mayor DENTRO de los pasos que este usuario ya tiene inicializados
        (no `completed_step_order + 1` a secas): el externo-invitado solo
        tiene filas de progreso para vídeo (order 1) y manual (order 4) —
        el "siguiente" tras completar el vídeo es manual, no el cuestionario
        (order 2, que ni siquiera existe para su onboarding parcial). Si no
        hay ningún paso `locked` por delante (era el último), no hace nada."""
        ...

    async def find_quiz_attempt(
        self, user_id: str, step_id: str
    ) -> Optional[QuizAttempt]: ...

    async def create_quiz_attempt(
        self,
        *,
        user_id: str,
        step_id: str,
        answers: dict[str, Any],
        score: float,
        passed: bool,
    ) -> QuizAttempt:
        """INSERT — debe traducir la violación de `UNIQUE(user_id, step_id)`
        a `QuizAlreadyAttemptedError` (nunca dejar que un 500 genérico
        llegue al cliente por esta carrera)."""
        ...

    async def mark_step_completed_if_operable(
        self, user_id: str, step_id: str, *, data: dict[str, Any]
    ) -> Optional[OnboardingProgress]:
        """UPDATE atómico condicionado a `status IN ('available',
        'in_progress')` -> `completed`, `progress_pct=100`. `None` si el
        paso ya no estaba operable (ya completado, o bloqueado por una
        carrera). Lo usan quiz (si pasa), firma, confirmación de manual y
        completar perfil."""
        ...

    async def find_active_document(self, kind: str) -> Optional[OnboardingDocument]:
        """El documento vigente (mayor `version`, `is_active=TRUE`) del tipo
        pedido — `None` si el admin todavía no lo ha configurado (Fase 5)."""
        ...

    async def create_signature(
        self,
        *,
        user_id: str,
        document_id: str,
        document_version: int,
        document_hash: str,
        signature_hash: str,
        signed_at: datetime,
        ip_address: str,
        user_agent: Optional[str],
    ) -> DocumentSignature: ...

    async def create_acknowledgement(
        self, *, user_id: str, document_id: str, ip_address: Optional[str]
    ) -> DocumentAcknowledgement: ...
