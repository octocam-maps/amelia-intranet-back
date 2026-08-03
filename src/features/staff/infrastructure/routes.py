"""Router de `/staff`: gestión de plantilla — exclusiva del admin
(docs/permisos-roles.md § "Gestión de plantilla"). Ni empleado ni
externo-invitado tienen ningún verbo sobre este recurso."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.shared.auth.dependencies import require_role
from src.shared.auth.roles import ADMIN_ONLY

from ..application.use_cases.create_staff_member import CreateStaffMemberUseCase
from ..application.use_cases.get_staff_role_history import GetStaffRoleHistoryUseCase
from ..application.use_cases.list_staff import ListStaffUseCase
from ..application.use_cases.update_staff_member import UpdateStaffMemberUseCase
from .dependencies import (
    get_create_staff_member_use_case,
    get_list_staff_use_case,
    get_staff_role_history_use_case,
    get_update_staff_member_use_case,
)
from .mappers import member_to_dto, members_to_dto, role_history_to_dto
from .schemas import (
    CreateStaffMemberDTO,
    RoleChangeListDTO,
    StaffMemberDTO,
    StaffMemberListDTO,
    UpdateStaffMemberDTO,
)


def create_staff_router() -> APIRouter:
    router = APIRouter(prefix="/staff", tags=["staff"])

    @router.get("", response_model=StaffMemberListDTO)
    async def list_staff(
        entity: Optional[str] = Query(None, description="Filtra por código de entidad (hub/lab/ops)"),
        search: Optional[str] = Query(None, description="Busca por nombre"),
        page: int = Query(1, ge=1),
        # BUG-2: el frontend (`StaffPage`/`TimeClockPage`, selector de persona)
        # pide una página "generosa" de hasta 200 para filtrar/paginar del
        # lado del cliente mientras no hay un contrato de paginación real
        # acordado — con `le=100` esa request de 200 devolvía 422 y la
        # pantalla de Plantilla se veía vacía (0 de 39 personas) sin ningún
        # aviso. 500 da margen sobre el techo actual del frontend (200) y
        # sobre la plantilla real (39) sin abrir la puerta a un page_size
        # arbitrariamente grande.
        page_size: int = Query(20, ge=1, le=500),
        current_user: dict = Depends(require_role(*ADMIN_ONLY)),
        use_case: ListStaffUseCase = Depends(get_list_staff_use_case),
    ):
        members, total = await use_case.execute(
            entity_code=entity, search=search, page=page, page_size=page_size
        )
        return members_to_dto(members, total)

    @router.post("", response_model=StaffMemberDTO, status_code=201)
    async def create_staff_member(
        dto: CreateStaffMemberDTO,
        current_user: dict = Depends(require_role(*ADMIN_ONLY)),
        use_case: CreateStaffMemberUseCase = Depends(get_create_staff_member_use_case),
    ):
        member = await use_case.execute(
            full_name=dto.full_name,
            email=dto.email,
            job_title=dto.job_title,
            contract_type=dto.contract_type,
            department=dto.department,
            entity_code=dto.entity,
            role_code=dto.role,
            hire_date=dto.hire_date,
            vacation_days_override=dto.vacation_days_override,
            invited_by=current_user["sub"],
        )
        return member_to_dto(member)

    @router.patch("/{user_id}", response_model=StaffMemberDTO)
    async def update_staff_member(
        user_id: str,
        dto: UpdateStaffMemberDTO,
        current_user: dict = Depends(require_role(*ADMIN_ONLY)),
        use_case: UpdateStaffMemberUseCase = Depends(get_update_staff_member_use_case),
    ):
        # `model_fields_set` distingue "el cliente no mandó
        # `vacation_days_override`" (no tocar el override) de "mandó
        # `vacation_days_override: null`" (vaciarlo -> automático) — un
        # `Optional[float] = None` por sí solo no puede (mismo patrón que
        # `holidays.update_holiday`).
        kwargs = {
            "job_title": dto.job_title,
            "department": dto.department,
            "entity_code": dto.entity,
            "role_code": dto.role,
            "is_active": dto.is_active,
            # Sin sentinela: `None` = no tocar. La fecha de alta se puede
            # fijar y corregir, pero no vaciar — ver `UpdateStaffMemberUseCase`.
            "hire_date": dto.hire_date,
            # Autor de la traza de `user_role_history` (039) cuando esta
            # petición cambie el rol.
            "changed_by": current_user["sub"],
        }
        if "vacation_days_override" in dto.model_fields_set:
            kwargs["vacation_days_override"] = dto.vacation_days_override
        # Mismo criterio para el tipo de contrato: ausente = no tocar,
        # `contract_type: null` explícito = dejarlo sin especificar.
        if "contract_type" in dto.model_fields_set:
            kwargs["contract_type"] = dto.contract_type
        member = await use_case.execute(user_id, **kwargs)
        return member_to_dto(member)

    @router.get("/{user_id}/role-history", response_model=RoleChangeListDTO)
    async def list_staff_role_history(
        user_id: str,
        current_user: dict = Depends(require_role(*ADMIN_ONLY)),
        use_case: GetStaffRoleHistoryUseCase = Depends(get_staff_role_history_use_case),
    ):
        """Historial de cambios de rol de una persona (`user_role_history`,
        migración 039) — de lo más reciente a lo más antiguo, incluida la fila
        de alta.

        ADMIN_ONLY como todo `/staff`: es un dato de gestión de personal, no algo
        que un trabajador deba poder consultar de un compañero. Ni siquiera se
        abre "el propio": nadie ha pedido ver su propio historial de roles, y
        abrirlo sin necesidad amplía la superficie de datos de plantilla
        expuesta.
        """
        changes = await use_case.execute(user_id)
        return role_history_to_dto(changes)

    return router
