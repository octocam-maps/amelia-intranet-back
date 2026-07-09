"""
Puerto (Protocol) del feature `staff`. `domain` no importa nada de
`infrastructure` ni de FastAPI — la implementación concreta (asyncpg) vive
en `infrastructure` y se inyecta aquí por duck typing estructural.
"""

from datetime import date
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
        vacation_days_per_year: Optional[float],
    ) -> StaffMember:
        """Crea el usuario con `status='invited'` (accede por primera vez
        con Google, igual que cualquier alta — 007_seed_initial_admin.sql)
        y, si se indica `vacation_days_per_year`, el saldo inicial del tipo
        `vacaciones` del año en curso."""
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
        vacation_days_per_year: Optional[float],
        status: Optional[str],
    ) -> Optional[StaffMember]:
        """Actualización parcial: cada parámetro en `None` significa "no
        tocar esta columna" (semántica PATCH), no "vaciarla"."""
        ...
