"""
Puerto (Protocol) del feature `staff`. `domain` no importa nada de
`infrastructure` ni de FastAPI — la implementación concreta (asyncpg) vive
en `infrastructure` y se inyecta aquí por duck typing estructural.
"""

from datetime import date, datetime
from typing import Optional, Protocol

from .entities import StaffMember


class IStaffRepository(Protocol):
    async def list_staff(
        self,
        *,
        entity_code: Optional[str],
        search: Optional[str],
        page: int,
        page_size: int,
    ) -> list[StaffMember]: ...

    async def count_staff(self, *, entity_code: Optional[str], search: Optional[str]) -> int: ...

    async def find_by_id(self, user_id: str) -> Optional[StaffMember]: ...

    async def find_by_email(self, email: str) -> Optional[StaffMember]: ...

    async def resolve_entity_id(self, entity_code: str) -> Optional[str]: ...

    async def resolve_role_id(self, role_code: str) -> Optional[str]: ...

    async def get_or_create_department_id(self, *, entity_id: str, department_name: str) -> str:
        """`departments` no tiene CRUD propio todavía (Fase 6) — el admin
        los va nombrando al dar de alta/editar personas; reutiliza el mismo
        `id` si ya existe uno con ese nombre en la misma entidad."""
        ...

    async def create_staff_member(
        self,
        *,
        full_name: str,
        email: str,
        job_title: Optional[str],
        department_id: Optional[str],
        entity_id: str,
        role_id: str,
        is_external: bool,
        hire_date: Optional[date],
        vacation_days_override: Optional[float],
        invited_by: str,
        expires_at: datetime,
    ) -> StaffMember:
        """Crea el usuario con `status='invited'` (accede por primera vez
        con Google, igual que cualquier alta — 007_seed_initial_admin.sql).

        `vacation_days_override` es la INTENCIÓN del admin sobre el
        entitlement de vacaciones: `None` = automático (se calcula desde
        `hire_date`, ver `absences.domain.vacation_entitlement`); un valor
        concreto = override manual. En AMBOS casos se siembra el saldo
        inicial del tipo `vacaciones` del año en curso (resuelto vía
        `resolve_vacation_entitlement_days`) — a diferencia del
        comportamiento previo, que solo sembraba saldo si el admin escribía
        un número.

        En la MISMA transacción registra la fila de `invitations`
        (trazabilidad + feature `invitations` para reenviar/cancelar) —
        `invited_by` es el `id` del admin autenticado que da de alta,
        `expires_at` la fecha límite (`INVITATION_EXPIRES_DAYS`, calculada
        por el caso de uso)."""
        ...

    async def update_staff_member(
        self,
        user_id: str,
        *,
        job_title: Optional[str],
        department_id: Optional[str],
        entity_id: Optional[str],
        role_id: Optional[str],
        is_external: Optional[bool],
        vacation_days_override: Optional[float],
        clear_vacation_days_override: bool,
        status: Optional[str],
    ) -> Optional[StaffMember]:
        """Actualización parcial: cada parámetro en `None` significa "no
        tocar esta columna" (semántica PATCH), no "vaciarla" — EXCEPTO
        `vacation_days_override`, que necesita distinguir tres estados
        ("no tocar" / "fijar un valor" / "volver a automático") con un
        `None` solo. `clear_vacation_days_override=True` es lo que fuerza
        "volver a automático" (mismo patrón que `holidays.clear_entity`):
        cuando es `True`, `vacation_days_override` (el valor) se ignora y la
        columna se vacía a NULL.

        Tanto si se fija como si se vacía el override, se recalcula y
        reescribe el saldo (`absence_balances.entitled_days`) del tipo
        `vacaciones` del año en curso — así el contador queda coherente de
        inmediato, sin esperar a la próxima lectura lazy
        (`get_or_create_balance`)."""
        ...


class ISessionRevoker(Protocol):
    """Puerto mínimo (defensa en profundidad de AUTHN-2): al suspender a
    alguien, además del corte inmediato por `ensure_user_is_active` en
    cada request (`src/shared/auth/dependencies.py`), conviene revocar
    también sus refresh tokens vigentes para que no pueda sacar un access
    token NUEVO vía `/auth/refresh` mientras el suspendido dure.

    `refresh_session.py` YA rechaza a un usuario `suspended` (chequea
    `user.status` antes de rotar), así que esto es belt-and-suspenders, no
    la defensa principal — de ahí que sea opcional (`Optional[...] = None`
    en `UpdateStaffMemberUseCase`) y no bloquee el caso de uso si no se
    inyecta.

    Forma estructural idéntica a `features.auth.domain.ports.ISessionRepository.
    revoke_all_sessions_for_user` — `staff.domain` NO importa `auth.domain`
    (evita acoplar dos features en la capa de dominio); el adaptador real
    (`PostgresSessionRepository`) se inyecta en
    `staff/infrastructure/dependencies.py`, que sí puede componer con otro
    feature (mismo patrón que `documents/infrastructure/dependencies.py`
    reutilizando `PostgresStaffRepository`)."""

    async def revoke_all_sessions_for_user(self, user_id: str) -> int: ...
