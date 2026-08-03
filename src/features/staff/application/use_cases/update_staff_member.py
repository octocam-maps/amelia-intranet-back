"""Caso de uso: editar una persona de la plantilla — puesto, departamento,
entidad, rol, fecha de alta, override de vacaciones/año y estado
(activo/suspendido).
Actualización parcial: solo se tocan los campos que llegan informados."""

from datetime import date
from typing import Any, Optional

from src.shared.auth.roles import RoleCode

from ...domain.entities import StaffMember
from ...domain.errors import (
    InvalidEntityCodeError,
    InvalidRoleCodeError,
    StaffMemberNotFoundError,
)
from ...domain.ports import ISessionRevoker, IStaffRepository

# Sentinela: distingue "no me pasaron vacation_days_override" (no tocar el
# override) de "me pasaron vacation_days_override=None explícitamente"
# (vaciarlo -> vuelve al cálculo automático desde `hire_date`). Mismo patrón
# que `holidays.UpdateHolidayUseCase._NOT_SET`.
_NOT_SET = object()


class UpdateStaffMemberUseCase:
    def __init__(
        self,
        repository: IStaffRepository,
        session_revoker: Optional[ISessionRevoker] = None,
    ):
        self._repository = repository
        # Opcional a propósito (defensa en profundidad de AUTHN-2, no la
        # defensa principal): si no se inyecta, suspender sigue funcionando
        # igual que antes, solo sin revocar sesiones de refresh.
        self._session_revoker = session_revoker

    async def execute(
        self,
        user_id: str,
        *,
        job_title: Optional[str] = None,
        # `_NOT_SET` distingue "no vino informado" de `None` explícito
        # (= vaciar). Ver el bloque de resolución más abajo.
        contract_type: Any = _NOT_SET,
        department: Optional[str] = None,
        entity_code: Optional[str] = None,
        role_code: Optional[str] = None,
        vacation_days_override: Optional[float] = _NOT_SET,  # type: ignore[assignment]
        is_active: Optional[bool] = None,
        # La fecha de alta DEJA DE SER INMUTABLE (decisión del team-lead,
        # 2026-08-03). Antes solo podía fijarse al crear a la persona, y el
        # formulario de edición la mostraba deshabilitada.
        #
        # POR QUÉ CAMBIA: quien se sembró por migración antes de que existiera
        # la columna (`007_seed_initial_admin.sql`, la columna llegó en la
        # `015`) se quedó con `hire_date` NULL y sin forma de rellenarla. Y con
        # `hire_date` NULL el entitlement de vacaciones es 0 días
        # (`FALLBACK_DAYS_WHEN_HIRE_DATE_UNKNOWN`), así que esas personas —el
        # administrador entre ellas— no pueden solicitar ni un día. La
        # inmutabilidad protegía la antigüedad de un cambio accidental, pero
        # dejaba sin salida a quien nunca la tuvo.
        #
        # NO SE PUEDE VACIAR, solo fijar: `None` significa "no tocar", nunca
        # "borrar la fecha". Vaciarla devolvería el saldo a 0 y tiraría la
        # antigüedad; corregir una fecha mal puesta se hace escribiendo otra.
        # Por eso aquí NO hay sentinela `_NOT_SET` como en el override.
        hire_date: Optional[date] = None,
        changed_by: Optional[str] = None,
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
            is_external = role_code == RoleCode.EXTERNO_INVITADO

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

        # Mismo esquema de tres estados para el tipo de contrato: `_NOT_SET` no
        # lo toca, `None` explícito lo vacía (vuelve a "sin especificar"), y un
        # valor lo fija. Sin el vaciado, un tipo puesto por error sería
        # irreversible desde el formulario.
        if contract_type is _NOT_SET:
            clear_contract_type = False
            effective_contract_type: Optional[str] = None
        elif contract_type is None:
            clear_contract_type = True
            effective_contract_type = None
        else:
            clear_contract_type = False
            effective_contract_type = contract_type

        updated = await self._repository.update_staff_member(
            user_id,
            job_title=job_title,
            contract_type=effective_contract_type,
            clear_contract_type=clear_contract_type,
            department_id=department_id,
            entity_id=entity_id,
            role_id=role_id,
            is_external=is_external,
            vacation_days_override=effective_override,
            clear_vacation_days_override=clear_vacation_days_override,
            status=status,
            hire_date=hire_date,
            changed_by=changed_by,
        )
        if updated is None:
            raise StaffMemberNotFoundError("La persona no existe.")

        # Defensa en profundidad de AUTHN-2: el corte de acceso YA es
        # inmediato vía `ensure_user_is_active` (SELECT por request en
        # `get_current_user`); esto además impide que el suspendido saque
        # un access token NUEVO vía `/auth/refresh` mientras dure suspendido
        # (`refresh_session.py` ya lo rechaza, pero revocar de una vez sus
        # sesiones evita depender solo de esa comprobación).
        #
        # Y TAMBIÉN al cambiar de rol (RF-A10.6): el `role` viaja DENTRO del
        # access token, así que sin revocar, un becario recién promocionado
        # seguiría arrastrando `role: becario` hasta 15 minutos — el navbar no le
        # mostraría Control horario y el backend le seguiría dando 403, con el
        # cambio ya guardado en BD. Al revés es peor: a quien se le RETIRA un
        # permiso, ese token viejo se lo mantendría vivo un cuarto de hora.
        role_changed = role_code is not None and role_code != member.role_code
        should_revoke = status == "suspended" or role_changed
        if should_revoke and self._session_revoker is not None:
            await self._session_revoker.revoke_all_sessions_for_user(user_id)

        return updated
