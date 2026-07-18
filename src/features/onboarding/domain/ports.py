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
    EmployeeOnboardingSnapshot,
    OnboardingDocument,
    OnboardingProgress,
    OnboardingStep,
    ProfileCompletionData,
    QuizAttempt,
)


class IOnboardingRepository(Protocol):
    async def list_active_steps(self) -> list[OnboardingStep]:
        """Catálogo completo (los 5 pasos), ordenado por `step_order`."""
        ...

    async def list_all_steps(self) -> list[OnboardingStep]:
        """Catálogo COMPLETO sin filtrar por `is_active` — a diferencia de
        `list_active_steps`, el admin (Fase 5) necesita ver también los
        pasos desactivados para poder reactivarlos."""
        ...

    async def find_step_by_id(self, step_id: str) -> Optional[OnboardingStep]: ...

    async def update_step(
        self, step_id: str, *, title: str, is_active: bool, config: dict[str, Any]
    ) -> Optional[OnboardingStep]:
        """UPDATE atómico del paso — el use case ya resolvió los valores
        finales (merge de lo enviado con lo existente) antes de llamar
        aquí, así que los tres campos son obligatorios y no hay ambigüedad
        de "no tocar" vs. "poner NULL" en el `config` JSONB. `None` si el
        `step_id` no existe (carrera con un borrado, no debería pasar hoy
        porque no hay DELETE de pasos)."""
        ...

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

    async def list_employee_progress_snapshots(self) -> list[EmployeeOnboardingSnapshot]:
        """Una fila por usuario interno/externo-invitado (no borrado),
        con SUS filas de progreso ya unidas a su paso (`LEFT JOIN` —
        `steps=[]` si el usuario nunca inicializó su progreso). El cálculo
        de `status`/`current_step_title` es lógica de dominio pura
        (`summarize_employee_onboarding`), no vive aquí."""
        ...

    async def reset_quiz_attempt(
        self, user_id: str, step_id: str
    ) -> Optional[OnboardingProgress]:
        """Override de admin: borra el intento de cuestionario de este
        usuario (`onboarding_quiz_attempts`) y reabre su progreso en este
        paso (`available`, `progress_pct=0`, `completed_at=NULL`) en UNA
        transacción — el intento único (`UNIQUE(user_id, step_id)`) solo
        se puede reabrir borrando la fila que lo bloquea. `None` si el
        usuario no tenía progreso inicializado en este paso (nada que
        reabrir)."""
        ...

    async def department_exists(self, department_id: str) -> bool:
        """Referencia real a `departments` (el desplegable del paso 5 es
        solo UI) — el use case la consulta ANTES de escribir
        `users.department_id`, para no dejar que una FK violation
        genérica llegue como 500."""
        ...

    async def save_profile_completion(
        self, user_id: str, profile: ProfileCompletionData
    ) -> bool:
        """Persiste los datos REALES del paso 5 en `users` (nombre
        completo + departamento) y `user_profiles` (DNI/NIE, fecha de
        nacimiento, móviles, dirección) en UNA transacción — a diferencia
        del borrador anterior, ya no se guardan en el JSONB de
        `onboarding_progress.data` (evita duplicar PII fuera de su tabla
        RGPD). `False` si el usuario no existe/está borrado (defensivo:
        no debería pasar con un JWT válido)."""
        ...
