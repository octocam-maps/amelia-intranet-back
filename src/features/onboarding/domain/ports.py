"""
Puertos (Protocols) del feature `onboarding`. `domain` no importa nada de
`infrastructure` ni de FastAPI — la implementación concreta (asyncpg) vive
en `infrastructure` y se inyecta aquí por duck typing estructural.
"""

from typing import Any, Optional, Protocol

from .entities import (
    DocumentAcknowledgement,
    EmployeeOnboardingSnapshot,
    OnboardingDocument,
    OnboardingDocumentUpload,
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
    ) -> Optional[QuizAttempt]:
        """El intento MÁS RECIENTE (mayor `attempt_number`) — `None` si no hay
        ninguno. Con dos intentos posibles ya no es "el intento", así que para
        decidir si quedan usa `count_quiz_attempts`, no esto."""
        ...

    async def count_quiz_attempts(self, user_id: str, step_id: str) -> int:
        """Cuántos intentos lleva gastados este usuario en este paso — lo que
        `ensure_quiz_attempts_left` compara contra `MAX_QUIZ_ATTEMPTS`."""
        ...

    async def create_quiz_attempt(
        self,
        *,
        user_id: str,
        step_id: str,
        answers: dict[str, Any],
        score: float,
        passed: bool,
        attempt_number: int,
    ) -> QuizAttempt:
        """INSERT — debe traducir la violación de
        `UNIQUE(user_id, step_id, attempt_number)` a
        `QuizAlreadyAttemptedError` (nunca dejar que un 500 genérico llegue al
        cliente por esta carrera). Esa UNIQUE es la que impide que dos
        peticiones simultáneas consuman el mismo número de intento y se salten
        el techo de `MAX_QUIZ_ATTEMPTS`."""
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

    async def find_active_documents(self, kind: str) -> list[OnboardingDocument]:
        """Los documentos vigentes (`is_active=TRUE`) del tipo pedido, en orden
        de lectura (`display_order`, migración 040). Lista vacía si el admin
        todavía no ha configurado ninguno.

        PLURAL desde la 040: el paso de manuales admite varios y su orden define
        la cascada. El `signature` sigue siendo uno solo, y quien lo consume toma
        el primero — mantenerlo en la misma firma evita dos caminos para leer la
        misma tabla."""
        ...

    async def list_manuals_library(self) -> list[OnboardingDocument]:
        """TODOS los manuales activos, obligatorios o no — la biblioteca de
        consulta (migración 043).

        Distinto de `find_active_documents('manual')`, que solo devuelve los de la
        CASCADA del paso 3. La biblioteca es un superconjunto: incluye el manual de
        uso de la intranet, que se consulta pero no se exige leer."""
        ...

    async def list_acknowledged_document_ids(self, user_id: str, kind: str) -> set[str]:
        """Ids de documentos de ese `kind` que este usuario YA confirmó
        (`document_acknowledgements`). Devuelve un `set` porque quien lo consume
        solo pregunta pertenencia, nunca orden — el orden lo da
        `find_active_documents`."""
        ...

    async def list_uploaded_document_ids(self, user_id: str) -> set[str]:
        """Ids de documentos `signature` para los que este usuario YA subió su
        PDF firmado (`onboarding_document_uploads`).

        El equivalente del paso 5 a `list_acknowledged_document_ids` del paso 3:
        allí "satisfecho" es haber confirmado la lectura, aquí es haber subido el
        documento firmado. Hacen falta las dos porque son tablas distintas —
        `document_acknowledgements` no sabe nada de subidas.

        Sin parámetro `kind`: `onboarding_document_uploads` solo se alimenta desde
        el paso de firma, así que filtrar por tipo no descartaría ninguna fila y
        obligaría a un JOIN que no aporta."""
        ...

    async def create_document_upload(
        self, *, user_id: str, onboarding_document_id: str, employee_document_id: str
    ) -> OnboardingDocumentUpload:
        """INSERT en `onboarding_document_uploads` — enlace, no trazabilidad
        (sin IP/hash: el propio `employee_documents` ya guarda cuándo y quién
        subió el binario). `UNIQUE(user_id, onboarding_document_id)` es la
        garantía real bajo concurrencia de que un mismo requisito no se
        satisface dos veces."""
        ...

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

    async def department_valid_for_user(
        self, department_id: str, user_id: str
    ) -> bool:
        """El departamento existe Y pertenece a la entidad del usuario.

        Antes solo comprobaba que EXISTIERA (`department_exists`), y eso dejaba
        pasar el departamento de otra sociedad: los mismos cinco departamentos
        están repetidos en las cuatro entidades del grupo, así que alguien de
        Amelia Hub podía quedar asignado al «Ingeniería» de Amelia Ops. Como el
        organigrama cuelga de `users.department_id`, el dato quedaba incoherente
        sin que nada avisara.

        Hace falta aquí ADEMÁS del filtro del listado: el desplegable es solo UI
        y enviar otro `department_id` a mano se salta cualquier candado del
        cliente (regla del proyecto: ocultar ≠ proteger).

        Se consulta ANTES de escribir `users.department_id` para no dejar que una
        violación de FK genérica llegue como 500.

        `True` si el usuario no tiene entidad (`users.entity_id IS NULL`): no
        hay con qué comparar y bloquearlo lo dejaría sin poder completar el paso.
        """
        ...

    async def find_user_full_name(self, user_id: str) -> Optional[str]:
        """Nombre para el copy del aviso `onboarding_completed`. Antes se
        tomaba del payload del paso de perfil, pero ese paso ya no es el que
        cierra el flujo (reordenación v1.1): quien lo cierra es la subida de
        documentación, que no trae ningún nombre. `None` si el usuario no
        existe/está borrado — el aviso cae a un genérico en vez de romper."""
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
