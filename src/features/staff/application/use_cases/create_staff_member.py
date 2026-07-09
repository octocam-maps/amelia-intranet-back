"""Caso de uso: alta de una persona en la plantilla
(docs/deck-fase6/10-editar-persona.png — mismo modal para alta y edición).
Crea el usuario con `status='invited'`: transiciona a `active` en su
primer login con Google, igual que cualquier alta existente
(007_seed_initial_admin.sql)."""

from datetime import date
from typing import Optional

from ...domain.entities import StaffMember
from ...domain.errors import (
    InvalidEntityCodeError,
    InvalidRoleCodeError,
    StaffEmailAlreadyExistsError,
)
from ...domain.ports import IStaffRepository


class CreateStaffMemberUseCase:
    def __init__(self, repository: IStaffRepository):
        self._repository = repository

    async def execute(
        self,
        *,
        full_name: str,
        email: str,
        job_title: Optional[str],
        department: Optional[str],
        entity_code: str,
        role_code: str,
        hire_date: Optional[date],
        vacation_days_per_year: Optional[float],
    ) -> StaffMember:
        normalized_email = email.strip().lower()
        if await self._repository.find_by_email(normalized_email) is not None:
            raise StaffEmailAlreadyExistsError("Ya existe una persona con ese correo.")

        entity_id = await self._repository.resolve_entity_id(entity_code)
        if entity_id is None:
            raise InvalidEntityCodeError(f"La entidad '{entity_code}' no existe.")

        role_id = await self._repository.resolve_role_id(role_code)
        if role_id is None:
            raise InvalidRoleCodeError(f"El rol '{role_code}' no existe.")

        department_id = None
        if department:
            department_id = await self._repository.get_or_create_department_id(
                entity_id=entity_id, department_name=department
            )

        return await self._repository.create_staff_member(
            full_name=full_name,
            email=normalized_email,
            job_title=job_title,
            department_id=department_id,
            entity_id=entity_id,
            role_id=role_id,
            is_external=role_code == "externo_invitado",
            hire_date=hire_date,
            vacation_days_per_year=vacation_days_per_year,
        )
