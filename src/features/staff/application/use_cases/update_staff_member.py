"""Caso de uso: editar una persona de la plantilla — puesto, departamento,
entidad, rol, override de vacaciones/año y estado (activo/suspendido).
Actualización parcial: solo se tocan los campos que llegan informados."""

from typing import Optional

from ...domain.entities import StaffMember
from ...domain.errors import (
    InvalidEntityCodeError,
    InvalidRoleCodeError,
    StaffMemberNotFoundError,
)
from ...domain.ports import IStaffRepository

# Sentinela: distingue "no me pasaron vacation_days_override" (no tocar el
# override) de "me pasaron vacation_days_override=None explícitamente"
# (vaciarlo -> vuelve al cálculo automático desde `hire_date`). Mismo patrón
# que `holidays.UpdateHolidayUseCase._NOT_SET`.
_NOT_SET = object()


class UpdateStaffMemberUseCase:
    def __init__(self, repository: IStaffRepository):
        self._repository = repository

    async def execute(
        self,
        user_id: str,
        *,
        job_title: Optional[str] = None,
        department: Optional[str] = None,
        entity_code: Optional[str] = None,
        role_code: Optional[str] = None,
        vacation_days_override: Optional[float] = _NOT_SET,  # type: ignore[assignment]
        is_active: Optional[bool] = None,
    ) -> StaffMember:
        member = await self._repository.find_by_id(user_id)
        if member is None:
            raise StaffMemberNotFoundError("La persona no existe.")

        entity_id: Optional[str] = None
        if entity_code is not None:
            entity_id = await self._repository.resolve_entity_id(entity_code)
            if entity_id is None:
                raise InvalidEntityCodeError(f"La entidad '{entity_code}' no existe.")

        role_id: Optional[str] = None
        is_external: Optional[bool] = None
        if role_code is not None:
            role_id = await self._repository.resolve_role_id(role_code)
            if role_id is None:
                raise InvalidRoleCodeError(f"El rol '{role_code}' no existe.")
            is_external = role_code == "externo_invitado"

        department_id: Optional[str] = None
        if department is not None:
            # El departamento vive dentro de una entidad: si esta misma
            # petición también cambia la entidad, usa la nueva; si no, la
            # que ya tenía la persona.
            target_entity_id = entity_id or member.entity_id
            if target_entity_id is None:
                raise InvalidEntityCodeError(
                    "No se puede asignar un departamento sin una entidad."
                )
            department_id = await self._repository.get_or_create_department_id(
                entity_id=target_entity_id, department_name=department
            )

        # "Estado activo" del modal es un toggle binario — al desactivar
        # pierde acceso (docs/deck-fase6/10-editar-persona.png).
        status = None
        if is_active is not None:
            status = "active" if is_active else "suspended"

        # `_NOT_SET` (no vino informado) -> no tocar el override, ni fijado
        # ni vaciado. `None` explícito -> vaciarlo (vuelve a automático).
        # Cualquier otro valor -> fijar ese override.
        if vacation_days_override is _NOT_SET:
            clear_vacation_days_override = False
            effective_override: Optional[float] = None
        elif vacation_days_override is None:
            clear_vacation_days_override = True
            effective_override = None
        else:
            clear_vacation_days_override = False
            effective_override = vacation_days_override

        updated = await self._repository.update_staff_member(
            user_id,
            job_title=job_title,
            department_id=department_id,
            entity_id=entity_id,
            role_id=role_id,
            is_external=is_external,
            vacation_days_override=effective_override,
            clear_vacation_days_override=clear_vacation_days_override,
            status=status,
        )
        if updated is None:
            raise StaffMemberNotFoundError("La persona no existe.")
        return updated
