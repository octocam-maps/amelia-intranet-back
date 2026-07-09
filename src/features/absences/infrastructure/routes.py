"""Router de `/absences`: tipos, saldo, solicitudes y bandeja de aprobación del admin."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.shared.auth.dependencies import require_role

from ..application.use_cases.create_absence_request import CreateAbsenceRequestUseCase
from ..application.use_cases.get_absence_balance import GetAbsenceBalanceUseCase
from ..application.use_cases.list_absence_requests import ListAbsenceRequestsUseCase
from ..application.use_cases.list_absence_types import ListAbsenceTypesUseCase
from ..application.use_cases.review_absence_request import ReviewAbsenceRequestUseCase
from .dependencies import (
    get_absence_balance_use_case,
    get_create_absence_request_use_case,
    get_list_absence_requests_use_case,
    get_list_absence_types_use_case,
    get_review_absence_request_use_case,
)
from .mappers import balances_to_dto, request_to_dto, requests_to_dto, types_to_dto
from .schemas import (
    AbsenceBalanceListDTO,
    AbsenceRequestDTO,
    AbsenceRequestListDTO,
    AbsenceTypeListDTO,
    CreateAbsenceRequestDTO,
    ReviewAbsenceRequestDTO,
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
