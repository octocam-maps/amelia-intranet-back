"""Router de `/absences`: tipos, saldo, solicitudes, bandeja de aprobación y
calendario general de la plantilla (todos exclusivos del admin, salvo lo
propio del empleado)."""

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from src.shared.auth.dependencies import require_role
from src.shared.utils.timezone import today_in_madrid

from ..application.use_cases.create_absence_request import CreateAbsenceRequestUseCase
from ..application.use_cases.create_absence_type import CreateAbsenceTypeUseCase
from ..application.use_cases.get_absence_balance import GetAbsenceBalanceUseCase
from ..application.use_cases.get_absence_calendar import GetAbsenceCalendarUseCase
from ..application.use_cases.list_absence_requests import ListAbsenceRequestsUseCase
from ..application.use_cases.list_absence_types import ListAbsenceTypesUseCase
from ..application.use_cases.list_all_absence_types import ListAllAbsenceTypesUseCase
from ..application.use_cases.review_absence_request import ReviewAbsenceRequestUseCase
from ..application.use_cases.update_absence_type import UpdateAbsenceTypeUseCase
from .calendar_pdf_export import build_absence_calendar_export_pdf
from .calendar_xlsx_export import build_absence_calendar_export_workbook
from .dependencies import (
    get_absence_balance_use_case,
    get_absence_calendar_use_case,
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
    calendar_entries_to_dto,
    request_to_dto,
    requests_to_dto,
    type_to_admin_dto,
    types_to_admin_dto,
    types_to_dto,
)
from .schemas import (
    AbsenceBalanceListDTO,
    AbsenceCalendarEntryListDTO,
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


def _resolve_calendar_range(
    date_from: Optional[date], date_to: Optional[date]
) -> tuple[date, date]:
    """Sin parámetros -> mes visible en curso (hora de Madrid, mismo
    criterio TZ que `time_clock/infrastructure/routes.py::_resolve_range`),
    que es el rango por defecto que pinta la pantalla del calendario
    general al abrirla."""
    if date_from and date_to:
        return date_from, date_to
    today = today_in_madrid()
    first_day = today.replace(day=1)
    next_month_first_day = (
        first_day.replace(year=first_day.year + 1, month=1)
        if first_day.month == 12
        else first_day.replace(month=first_day.month + 1)
    )
    last_day = next_month_first_day - timedelta(days=1)
    return date_from or first_day, date_to or last_day


def create_absences_router() -> APIRouter:
    router = APIRouter(prefix="/absences", tags=["absences"])

    # El externo-invitado no tiene "Ausencias" en la matriz de permisos
    # (docs/permisos-roles.md: ❌) — se rechaza aquí, en el backend, no solo
    # ocultando el ítem del navbar.
    @router.get("/types", response_model=AbsenceTypeListDTO)
    async def list_types(
        # `socio` [migración 024] = igual que empleado en TODO lo propio
        # (tipos, saldo, alta y listado de sus propias solicitudes) — la
        # visión global/exportación del calendario general es un permiso
        # ADICIONAL (ver los 3 endpoints `/calendar/*` más abajo), no un
        # reemplazo de este acceso de empleado.
        current_user: dict = Depends(require_role("administrador", "empleado", "socio")),
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
            requires_approval=dto.requires_approval,
            requires_justification=dto.requires_justification,
            max_days_per_year=dto.max_days_per_year,
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
            requires_approval=dto.requires_approval,
            requires_justification=dto.requires_justification,
            max_days_per_year=dto.max_days_per_year,
        )
        return type_to_admin_dto(absence_type)

    @router.get("/balance", response_model=AbsenceBalanceListDTO)
    async def get_balance(
        user_id: Optional[str] = Query(
            None, description="Solo el admin puede consultar el saldo de otro usuario"
        ),
        year: Optional[int] = Query(None),
        # `socio` [migración 024] = igual que empleado en TODO lo propio
        # (tipos, saldo, alta y listado de sus propias solicitudes) — la
        # visión global/exportación del calendario general es un permiso
        # ADICIONAL (ver los 3 endpoints `/calendar/*` más abajo), no un
        # reemplazo de este acceso de empleado.
        current_user: dict = Depends(require_role("administrador", "empleado", "socio")),
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
        # `socio` [migración 024] = igual que empleado en TODO lo propio
        # (tipos, saldo, alta y listado de sus propias solicitudes) — la
        # visión global/exportación del calendario general es un permiso
        # ADICIONAL (ver los 3 endpoints `/calendar/*` más abajo), no un
        # reemplazo de este acceso de empleado.
        current_user: dict = Depends(require_role("administrador", "empleado", "socio")),
        use_case: CreateAbsenceRequestUseCase = Depends(get_create_absence_request_use_case),
    ):
        """Autoaprobación del administrador (B-1c, docs/permisos-roles.md §
        Ausencias): `requester_role` viaja al caso de uso para que la
        solicitud del admin nazca ya `approved`, sin pasar por la bandeja de
        revisión — se decide en `application`, no aquí."""
        request = await use_case.execute(
            user_id=current_user["sub"],
            requester_role=current_user["role"],
            absence_type_id=dto.absence_type_id,
            start_date=dto.start_date,
            end_date=dto.end_date,
            reason=dto.reason,
        )
        return request_to_dto(request)

    @router.get("/requests", response_model=AbsenceRequestListDTO)
    async def list_requests(
        user_id: Optional[str] = Query(None),
        # `socio` [migración 024] = igual que empleado en TODO lo propio
        # (tipos, saldo, alta y listado de sus propias solicitudes) — la
        # visión global/exportación del calendario general es un permiso
        # ADICIONAL (ver los 3 endpoints `/calendar/*` más abajo), no un
        # reemplazo de este acceso de empleado.
        current_user: dict = Depends(require_role("administrador", "empleado", "socio")),
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

    # --- Calendario general de la plantilla (LOTE 4) — admin + socio.
    # A diferencia de `/requests/all` (histórico completo del gantt ya
    # existente en Ausencias > gestión), estos 3 endpoints comparten el
    # mismo rango de fechas (mes visible por defecto) y solo devuelven
    # `pending`/`approved` — ver `GetAbsenceCalendarUseCase`.
    #
    # `socio` [migración 024] tiene visión global de este calendario (ver +
    # exportar) igual que el admin, pero NO el resto de "Administración"
    # (aprobar ausencias, festivos, tipos de ausencia, buzón, onboarding
    # admin, plantilla) — esos endpoints siguen `require_role("administrador")`
    # exclusivamente, sin tocar. ---

    @router.get("/calendar/all", response_model=AbsenceCalendarEntryListDTO)
    async def get_calendar_all(
        date_from: Optional[date] = Query(None),
        date_to: Optional[date] = Query(None),
        current_user: dict = Depends(require_role("administrador", "socio")),
        use_case: GetAbsenceCalendarUseCase = Depends(get_absence_calendar_use_case),
    ):
        """Calendario general de RRHH: TODOS los empleados, acotado por
        rango de fechas. RBAC real vía `require_role`, no solo un ítem
        oculto del navbar (docs/permisos-roles.md § reglas)."""
        resolved_from, resolved_to = _resolve_calendar_range(date_from, date_to)
        entries = await use_case.execute(
            requester_role=current_user["role"], date_from=resolved_from, date_to=resolved_to
        )
        return calendar_entries_to_dto(entries)

    @router.get("/calendar/export.xlsx")
    async def export_calendar_xlsx(
        date_from: Optional[date] = Query(None),
        date_to: Optional[date] = Query(None),
        current_user: dict = Depends(require_role("administrador", "socio")),
        use_case: GetAbsenceCalendarUseCase = Depends(get_absence_calendar_use_case),
    ):
        """Informe XLSX con logo de marca del calendario general — mismo
        patrón que `time-clock/entries/export.xlsx` (logo, cabecera navy,
        panel congelado)."""
        resolved_from, resolved_to = _resolve_calendar_range(date_from, date_to)
        entries = await use_case.execute(
            requester_role=current_user["role"], date_from=resolved_from, date_to=resolved_to
        )
        workbook_bytes = build_absence_calendar_export_workbook(
            entries, date_from=resolved_from, date_to=resolved_to
        )
        filename = f"calendario-ausencias-{resolved_from.isoformat()}_{resolved_to.isoformat()}.xlsx"
        return StreamingResponse(
            iter([workbook_bytes]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.get("/calendar/export.pdf")
    async def export_calendar_pdf(
        date_from: Optional[date] = Query(None),
        date_to: Optional[date] = Query(None),
        current_user: dict = Depends(require_role("administrador", "socio")),
        use_case: GetAbsenceCalendarUseCase = Depends(get_absence_calendar_use_case),
    ):
        """Informe PDF con logo de marca del calendario general —
        `reportlab` (ver `calendar_pdf_export.py`)."""
        resolved_from, resolved_to = _resolve_calendar_range(date_from, date_to)
        entries = await use_case.execute(
            requester_role=current_user["role"], date_from=resolved_from, date_to=resolved_to
        )
        pdf_bytes = build_absence_calendar_export_pdf(
            entries, date_from=resolved_from, date_to=resolved_to
        )
        filename = f"calendario-ausencias-{resolved_from.isoformat()}_{resolved_to.isoformat()}.pdf"
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

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
