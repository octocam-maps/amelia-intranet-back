"""Router de `/absences`: tipos, saldo, solicitudes y bandeja de aprobación del admin."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.shared.auth.dependencies import require_role

from ..application.use_cases.create_absence_request import CreateAbsenceRequestUseCase
from ..application.use_cases.create_absence_type import CreateAbsenceTypeUseCase
from ..application.use_cases.get_absence_balance import GetAbsenceBalanceUseCase
from ..application.use_cases.list_absence_requests import ListAbsenceRequestsUseCase
from ..application.use_cases.list_absence_types import ListAbsenceTypesUseCase
from ..application.use_cases.list_all_absence_types import ListAllAbsenceTypesUseCase
from ..application.use_cases.review_absence_request import ReviewAbsenceRequestUseCase
from ..application.use_cases.update_absence_type import UpdateAbsenceTypeUseCase
from .dependencies import (
    get_absence_balance_use_case,
    get_create_absence_request_use_case,
    get_create_absence_type_use_case,
    get_list_absence_requests_use_case,
    get_list_absence_types_use_case,
    get_list_all_absence_types_use_case,
    get_review_absence_request_use_case,
    get_update_absence_type_use_case,
)
from .mappers import (
    balances_to_dto,
    request_to_dto,
    requests_to_dto,
    type_to_admin_dto,
    types_to_admin_dto,
    types_to_dto,
)
from .schemas import (
    AbsenceBalanceListDTO,
    AbsenceRequestDTO,
    AbsenceRequestListDTO,
    AbsenceTypeAdminDTO,
    AbsenceTypeAdminListDTO,
    AbsenceTypeListDTO,
    CreateAbsenceRequestDTO,
    CreateAbsenceTypeDTO,
    ReviewAbsenceRequestDTO,
    UpdateAbsenceTypeDTO,
)


def create_absences_router() -> APIRouter:
    router = APIRouter(prefix="/absences", tags=["absences"])

    # El externo-invitado no tiene "Ausencias" en la matriz de permisos
    # (docs/permisos-roles.md: ❌) — se rechaza aquí, en el backend, no solo
    # ocultando el ítem del navbar.
    @router.get("/types", response_model=AbsenceTypeListDTO)
    async def list_types(
        current_user: dict = Depends(require_role("administrador", "empleado")),
        use_case: ListAbsenceTypesUseCase = Depends(get_list_absence_types_use_case),
    ):
        types = await use_case.execute()
        return types_to_dto(types)

    @router.get("/types/admin", response_model=AbsenceTypeAdminListDTO)
    async def list_all_types(
        current_user: dict = Depends(require_role("administrador")),
        use_case: ListAllAbsenceTypesUseCase = Depends(get_list_all_absence_types_use_case),
    ):
        """Vista de gestión — incluye los tipos desactivados
        (docs/permisos-roles.md § "Tipos de ausencia"), a diferencia de
        `GET /types` (solo activos, para el modal de solicitud)."""
        types = await use_case.execute()
        return types_to_admin_dto(types)

    @router.post("/types", response_model=AbsenceTypeAdminDTO, status_code=201)
    async def create_type(
        dto: CreateAbsenceTypeDTO,
        current_user: dict = Depends(require_role("administrador")),
        use_case: CreateAbsenceTypeUseCase = Depends(get_create_absence_type_use_case),
    ):
        absence_type = await use_case.execute(
            code=dto.code,
            name=dto.name,
            is_paid=dto.is_paid,
            affects_balance=dto.affects_balance,
            default_entitled_days=dto.default_entitled_days,
            color=dto.color,
        )
        return type_to_admin_dto(absence_type)

    @router.patch("/types/{absence_type_id}", response_model=AbsenceTypeAdminDTO)
    async def update_type(
        absence_type_id: str,
        dto: UpdateAbsenceTypeDTO,
        current_user: dict = Depends(require_role("administrador")),
        use_case: UpdateAbsenceTypeUseCase = Depends(get_update_absence_type_use_case),
    ):
        """No hay DELETE: desactivar (`is_active=false`) es el único
        "borrado" — `absence_requests.absence_type_id` es `ON DELETE
        RESTRICT`, un tipo con solicitudes asociadas no se puede eliminar
        sin romper el histórico."""
        absence_type = await use_case.execute(
            absence_type_id,
            name=dto.name,
            is_paid=dto.is_paid,
            affects_balance=dto.affects_balance,
            default_entitled_days=dto.default_entitled_days,
            color=dto.color,
            is_active=dto.is_active,
        )
        return type_to_admin_dto(absence_type)

    @router.get("/balance", response_model=AbsenceBalanceListDTO)
    async def get_balance(
        user_id: Optional[str] = Query(
            None, description="Solo el admin puede consultar el saldo de otro usuario"
        ),
        year: Optional[int] = Query(None),
        current_user: dict = Depends(require_role("administrador", "empleado")),
        use_case: GetAbsenceBalanceUseCase = Depends(get_absence_balance_use_case),
    ):
        """Contador en tiempo real: entitled/used/pending/available por tipo."""
        balances = await use_case.execute(
            requester_id=current_user["sub"],
            requester_role=current_user["role"],
            target_user_id=user_id,
            year=year,
        )
        return balances_to_dto(balances)

    @router.post("/requests", response_model=AbsenceRequestDTO, status_code=201)
    async def create_request(
        dto: CreateAbsenceRequestDTO,
        current_user: dict = Depends(require_role("administrador", "empleado")),
        use_case: CreateAbsenceRequestUseCase = Depends(get_create_absence_request_use_case),
    ):
        request = await use_case.execute(
            user_id=current_user["sub"],
            absence_type_id=dto.absence_type_id,
            start_date=dto.start_date,
            end_date=dto.end_date,
            reason=dto.reason,
        )
        return request_to_dto(request)

    @router.get("/requests", response_model=AbsenceRequestListDTO)
    async def list_requests(
        user_id: Optional[str] = Query(None),
        current_user: dict = Depends(require_role("administrador", "empleado")),
        use_case: ListAbsenceRequestsUseCase = Depends(get_list_absence_requests_use_case),
    ):
        """Propias por defecto; el admin puede pasar `user_id` para ver las de otro."""
        requests = await use_case.execute(
            requester_id=current_user["sub"],
            requester_role=current_user["role"],
            mode="own",
            target_user_id=user_id,
        )
        return requests_to_dto(requests)

    @router.get("/requests/pending", response_model=AbsenceRequestListDTO)
    async def list_pending_requests(
        current_user: dict = Depends(require_role("administrador")),
        use_case: ListAbsenceRequestsUseCase = Depends(get_list_absence_requests_use_case),
    ):
        """Bandeja de aprobación — exclusiva del admin."""
        requests = await use_case.execute(
            requester_id=current_user["sub"], requester_role=current_user["role"], mode="pending"
        )
        return requests_to_dto(requests)

    @router.get("/requests/all", response_model=AbsenceRequestListDTO)
    async def list_all_requests(
        current_user: dict = Depends(require_role("administrador")),
        use_case: ListAbsenceRequestsUseCase = Depends(get_list_absence_requests_use_case),
    ):
        """Calendario global — exclusivo del admin (docs/permisos-roles.md § Ausencias)."""
        requests = await use_case.execute(
            requester_id=current_user["sub"], requester_role=current_user["role"], mode="all"
        )
        return requests_to_dto(requests)

    @router.post("/requests/{request_id}/review", response_model=AbsenceRequestDTO)
    async def review_request(
        request_id: str,
        dto: ReviewAbsenceRequestDTO,
        current_user: dict = Depends(require_role("administrador")),
        use_case: ReviewAbsenceRequestUseCase = Depends(get_review_absence_request_use_case),
    ):
        """Aprueba/rechaza — exclusivo del admin. RBAC real vía `require_role`,
        no solo un ítem oculto del navbar (docs/permisos-roles.md § reglas)."""
        request = await use_case.execute(
            request_id=request_id,
            reviewer_id=current_user["sub"],
            decision=dto.decision,
            note=dto.note,
        )
        return request_to_dto(request)

    return router
