"""
Puerto (Protocol) del feature `notifications`. `domain` no importa nada de
`infrastructure` ni de FastAPI — la implementación concreta (asyncpg) vive
en `infrastructure` y se inyecta aquí por duck typing estructural.

Además de leer/escribir `notifications`, este puerto expone proyecciones de
SOLO LECTURA sobre tablas de otros features (`users`, `user_profiles`,
`time_clock_entries`) para resolver destinatarios de fan-out y alimentar los
jobs por-tiempo — mismo patrón que `features/dashboard/domain/ports.py`.
"""

from datetime import date, datetime
from typing import Any, Optional, Protocol

from .entities import Notification


class INotificationRepository(Protocol):
    async def create(
        self, *, user_id: str, type: str, title: str, body: Optional[str], data: dict[str, Any]
    ) -> Notification: ...

    async def list_for_user(
        self, user_id: str, *, limit: int, before: Optional[datetime]
    ) -> list[Notification]:
        """`created_at DESC`. `before` es el cursor de paginación (excluye
        estrictamente notificaciones con `created_at >= before`)."""
        ...

    async def count_unread(self, user_id: str) -> int: ...

    async def mark_read(self, notification_id: str, user_id: str) -> Optional[Notification]:
        """`None` si no existe O no es del usuario — ver `NotificationNotFoundError`."""
        ...

    async def mark_all_read(self, user_id: str) -> int:
        """Devuelve cuántas filas se marcaron (las que estaban sin leer)."""
        ...

    # --- Resolución de destinatarios y trazabilidad de email ---

    async def find_email(self, user_id: str) -> Optional[str]:
        """`None` si el usuario no existe o está dado de baja (`deleted_at`) —
        `NotifyUseCase` simplemente no envía email a ese destinatario."""
        ...

    async def list_admin_ids(self) -> list[str]:
        """Administradores activos — hoy solo Beatriz, pero plural por diseño."""
        ...

    async def list_active_user_ids_excluding_role(self, role_code: str) -> list[str]:
        """Toda la plantilla activa salvo el rol indicado. Hoy solo la usa
        `notify_team_excluding_role`, que se mantiene como atajo genérico
        por si otro disparador necesita ese mismo recorte."""
        ...

    async def list_announcement_recipient_ids(
        self, *, audience: str, entity_id: Optional[str], role_id: Optional[str]
    ) -> list[str]:
        """Destinatarios del fan-out de `announcement_published`, ya
        acotados a la MISMA audiencia que el anuncio (`all`/`entity`/`role`)
        — plantilla activa y SIEMPRE excluyendo `externo_invitado`
        (docs/permisos-roles.md § Inicio: ❌ para externo). Si
        `audience='role'` apunta justo a ese rol excluido, la lista sale
        vacía — es el comportamiento correcto, no un bug."""
        ...

    # --- Proyecciones para los jobs por-tiempo (batch) ---

    async def list_birthday_user_ids(self, *, month: int, day: int) -> list[tuple[str, str]]:
        """`(user_id, full_name)` de quienes cumplen años hoy
        (`user_profiles.birth_date`), solo plantilla activa."""
        ...

    async def list_anniversary_users(self, *, month: int, day: int) -> list[tuple[str, int]]:
        """`(user_id, years)` de quienes hoy cumplen N años (N>=1) desde
        `users.hire_date`, solo plantilla activa."""
        ...

    async def list_user_ids_with_open_entry(self, work_date: date) -> list[str]:
        """Usuarios con un tramo de `work_date` sin `clock_out` — fichó
        entrada y no salida."""
        ...
