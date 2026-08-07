"""Router de `/time-clock`: fichaje por tramos manuales, historial y export CSV."""

import csv
import io
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from src.shared.auth.dependencies import require_role
from src.shared.auth.roles import ADMIN_ONLY, TECHNICIAN_ROLES, TIME_CLOCK_ROLES, RoleCode
from src.shared.utils.timezone import today_in_madrid

from ..domain.entities import OvernightStay, ProductCategory
from ..domain.errors import TimeClockForbiddenError

from ..application.use_cases.add_time_clock_entry_note import AddTimeClockEntryNoteUseCase
from ..application.use_cases.clock_in import ClockInUseCase
from ..application.use_cases.clock_out import ClockOutUseCase
from ..application.use_cases.create_technician_daily_log import (
    CreateTechnicianDailyLogUseCase,
)
from ..application.use_cases.create_time_clock_entries_batch import (
    CreateTimeClockEntriesBatchUseCase,
)
from ..application.use_cases.create_time_clock_entry import CreateTimeClockEntryUseCase
from ..application.use_cases.delete_technician_daily_log import (
    DeleteTechnicianDailyLogUseCase,
)
from ..application.use_cases.delete_time_clock_entry import DeleteTimeClockEntryUseCase
from ..application.use_cases.end_break import EndBreakUseCase
from ..application.use_cases.export_time_clock_entries import ExportTimeClockEntriesUseCase
from ..application.use_cases.get_compensation_balance import GetCompensationBalanceUseCase
from ..application.use_cases.get_live_status import GetLiveStatusUseCase
from ..application.use_cases.list_projects import ListProjectsUseCase
from ..application.use_cases.list_technician_daily_logs import (
    ListTechnicianDailyLogsUseCase,
)
from ..application.use_cases.list_time_clock_entries import ListTimeClockEntriesUseCase
from ..application.use_cases.list_time_clock_entry_notes import ListTimeClockEntryNotesUseCase
from ..application.use_cases.start_break import StartBreakUseCase
from ..application.use_cases.update_technician_daily_log import (
    UpdateTechnicianDailyLogUseCase,
)
from ..application.use_cases.update_time_clock_entry import UpdateTimeClockEntryUseCase
from .dependencies import (
    get_add_time_clock_entry_note_use_case,
    get_clock_in_use_case,
    get_clock_out_use_case,
    get_compensation_balance_use_case,
    get_create_technician_daily_log_use_case,
    get_create_time_clock_entries_batch_use_case,
    get_create_time_clock_entry_use_case,
    get_delete_technician_daily_log_use_case,
    get_delete_time_clock_entry_use_case,
    get_end_break_use_case,
    get_export_time_clock_entries_use_case,
    get_list_projects_use_case,
    get_list_technician_daily_logs_use_case,
    get_list_time_clock_entries_use_case,
    get_list_time_clock_entry_notes_use_case,
    get_live_status_use_case,
    get_start_break_use_case,
    get_update_technician_daily_log_use_case,
    get_update_time_clock_entry_use_case,
)
from .mappers import (
    batch_result_to_dto,
    compensation_balance_to_dto,
    daily_log_to_dto,
    daily_logs_to_dto,
    entries_to_dto,
    entry_to_dto,
    live_status_to_dto,
    note_to_dto,
    notes_to_dto,
    projects_to_dto,
)
from .technician_xlsx_export import build_technician_month_workbook, month_filename
from .schemas import (
    AddTimeClockEntryNoteDTO,
    CompensationBalanceDTO,
    CreateTimeClockEntriesBatchDTO,
    CreateTimeClockEntryDTO,
    ProjectListDTO,
    TechnicianDailyLogDTO,
    TechnicianDailyLogInputDTO,
    TechnicianDailyLogListDTO,
    UpdateTechnicianDailyLogDTO,
    TimeClockCurrentStatusDTO,
    TimeClockEntriesBatchDTO,
    TimeClockEntryDTO,
    TimeClockEntryListDTO,
    TimeClockEntryNoteDTO,
    TimeClockEntryNoteListDTO,
    UpdateTimeClockEntryDTO,
)
from .xlsx_export import (
    TITLE_ADMIN as XLSX_TITLE_ADMIN,
    TITLE_EMPLOYEE as XLSX_TITLE_EMPLOYEE,
    build_time_clock_export_workbook,
)

_DEFAULT_WINDOW_DAYS = 30
_DEFAULT_LIST_LIMIT = 50
_MAX_LIST_LIMIT = 200


def _resolve_range(date_from: Optional[date], date_to: Optional[date]) -> tuple[date, date]:
    # TZ-1: "hoy" del historial y del export es Europe/Madrid, no la TZ del
    # proceso (UTC) — evita que el último tramo del día "se pierda" de la
    # ventana por defecto justo alrededor de la medianoche.
    today = today_in_madrid()
    return date_from or (today - timedelta(days=_DEFAULT_WINDOW_DAYS)), date_to or today


def _parse_user_ids(raw: Optional[str]) -> Optional[list[str]]:
    """`user_ids` (multi-selector, Lote 2) viaja como CSV en la query string
    (`?user_ids=id1,id2`) — el guard RGPD (solo el admin puede pedir más de
    uno) vive en el use case, aquí solo se parsea."""
    if not raw:
        return None
    ids = [part.strip() for part in raw.split(",") if part.strip()]
    return ids or None


def create_time_clock_router() -> APIRouter:
    router = APIRouter(prefix="/time-clock", tags=["time-clock"])

    # El externo-invitado no tiene "Control horario" en la matriz de permisos
    # (docs/permisos-roles.md: ❌) — se rechaza aquí, en el backend, no solo
    # ocultando el ítem del navbar.
    #
    # El `becario` [migración 038, RF-A10] tampoco: es el ÚNICO módulo que se le
    # niega, y por eso este router usa `TIME_CLOCK_ROLES` en vez del
    # `INTERNAL_ROLES` que usa el resto del backend. Ojo al añadir un endpoint
    # aquí: copiar el `Depends` de un router vecino le daría acceso al becario
    # sin que nada falle.
    @router.post("/entries", response_model=TimeClockEntryDTO, status_code=201)
    async def create_entry(
        dto: CreateTimeClockEntryDTO,
        # `socio` [migración 024] = igual que empleado -> ficha su propio
        # horario como cualquier trabajador; solo `/entries/{id}/notes` (POST)
        # sigue exclusivo del admin (incidencia de RRHH, no del titular).
        current_user: dict = Depends(require_role(*TIME_CLOCK_ROLES)),
        use_case: CreateTimeClockEntryUseCase = Depends(get_create_time_clock_entry_use_case),
    ):
        """Registra un tramo — siempre para el propio usuario autenticado."""
        entry = await use_case.execute(
            user_id=current_user["sub"],
            work_date=dto.work_date,
            clock_in=dto.clock_in,
            clock_out=dto.clock_out,
        )
        return entry_to_dto(entry)

    @router.post("/entries/batch", response_model=TimeClockEntriesBatchDTO)
    async def create_entries_batch(
        dto: CreateTimeClockEntriesBatchDTO,
        # `socio` [migración 024] = igual que empleado -> ficha su propio
        # horario como cualquier trabajador.
        current_user: dict = Depends(require_role(*TIME_CLOCK_ROLES)),
        use_case: CreateTimeClockEntriesBatchUseCase = Depends(
            get_create_time_clock_entries_batch_use_case
        ),
    ):
        """Alta de fichaje en lote sobre un rango de hasta 7 días (RF-A3) —
        siempre para el propio usuario autenticado, igual que `POST /entries`
        (nadie ficha por otro). Respuesta SIEMPRE 200, nunca 201: el lote
        puede no crear nada (p.ej. una ausencia aprobada que cubre todo el
        rango) y seguir siendo un resultado válido — ver `created`/`omitted`.

        Un día laborable futuro sin ninguna exclusión de calendario que lo
        cubra rechaza la petición COMPLETA (422, LOGIC-2 — pentest ético,
        severidad ALTA): el error de dominio propaga sin desglose, nunca se
        llega a construir un `created`/`omitted` parcial."""
        result = await use_case.execute(
            user_id=current_user["sub"],
            entity_id=current_user.get("entity_id"),
            date_from=dto.date_from,
            date_to=dto.date_to,
            clock_in_time=dto.clock_in_time,
            clock_out_time=dto.clock_out_time,
        )
        return batch_result_to_dto(result)

    @router.get("/entries", response_model=TimeClockEntryListDTO)
    async def list_entries(
        user_id: Optional[str] = Query(None, description="Solo el admin puede consultar otro usuario"),
        user_ids: Optional[str] = Query(
            None,
            description=(
                "CSV de ids (multi-selector) — solo el admin puede pedir más de "
                "uno; gana sobre `user_id` si llegan los dos."
            ),
        ),
        date_from: Optional[date] = Query(None),
        date_to: Optional[date] = Query(None),
        limit: int = Query(_DEFAULT_LIST_LIMIT, ge=1, le=_MAX_LIST_LIMIT),
        offset: int = Query(0, ge=0),
        # `socio` [migración 024] = igual que empleado -> ficha su propio
        # horario como cualquier trabajador; solo `/entries/{id}/notes` (POST)
        # sigue exclusivo del admin (incidencia de RRHH, no del titular).
        current_user: dict = Depends(require_role(*TIME_CLOCK_ROLES)),
        use_case: ListTimeClockEntriesUseCase = Depends(get_list_time_clock_entries_use_case),
    ):
        """Historial de tramos, paginado (`limit`/`offset`). Sin `user_id`/
        `user_ids`: los propios (TODOS si el rol es admin) — ver X1/X2 del
        Lote 1 (feedback post-demo): ~850 tramos/mes eran demasiados para
        cargar de golpe, y el admin necesitaba poder acotar por persona(s)."""
        resolved_from, resolved_to = _resolve_range(date_from, date_to)
        page = await use_case.execute(
            requester_id=current_user["sub"],
            requester_role=current_user["role"],
            target_user_id=user_id,
            target_user_ids=_parse_user_ids(user_ids),
            date_from=resolved_from,
            date_to=resolved_to,
            limit=limit,
            offset=offset,
        )
        return entries_to_dto(page, limit=limit, offset=offset)

    @router.get("/entries/export")
    async def export_entries(
        user_id: Optional[str] = Query(None),
        user_ids: Optional[str] = Query(None, description="CSV de ids (multi-selector)"),
        date_from: Optional[date] = Query(None),
        date_to: Optional[date] = Query(None),
        # `socio` [migración 024] = igual que empleado -> ficha su propio
        # horario como cualquier trabajador; solo `/entries/{id}/notes` (POST)
        # sigue exclusivo del admin (incidencia de RRHH, no del titular).
        current_user: dict = Depends(require_role(*TIME_CLOCK_ROLES)),
        use_case: ListTimeClockEntriesUseCase = Depends(get_list_time_clock_entries_use_case),
    ):
        """Exportación básica en CSV del mismo listado de `GET /time-clock/entries`
        — a diferencia de ese endpoint, exporta TODO el rango sin paginar
        (`limit=None`), no solo la página que se ve en pantalla."""
        resolved_from, resolved_to = _resolve_range(date_from, date_to)
        page = await use_case.execute(
            requester_id=current_user["sub"],
            requester_role=current_user["role"],
            target_user_id=user_id,
            target_user_ids=_parse_user_ids(user_ids),
            date_from=resolved_from,
            date_to=resolved_to,
            limit=None,
            offset=0,
        )

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["fecha", "entrada", "salida", "minutos_trabajados", "origen"])
        for entry in page.items:
            writer.writerow(
                [
                    entry.work_date.isoformat(),
                    entry.clock_in.isoformat(),
                    entry.clock_out.isoformat() if entry.clock_out else "",
                    entry.worked_minutes if entry.worked_minutes is not None else "",
                    entry.source,
                ]
            )
        buffer.seek(0)
        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=fichaje.csv"},
        )

    @router.get("/entries/export.xlsx")
    async def export_entries_xlsx(
        # `socio` [migración 024] = igual que empleado -> ficha su propio
        # horario como cualquier trabajador; solo `/entries/{id}/notes` (POST)
        # sigue exclusivo del admin (incidencia de RRHH, no del titular).
        current_user: dict = Depends(require_role(*TIME_CLOCK_ROLES)),
        use_case: ExportTimeClockEntriesUseCase = Depends(get_export_time_clock_entries_use_case),
    ):
        """Informe XLSX con logo de marca de los fichajes, últimos 30 días —
        a diferencia de `GET /entries/export` (CSV, alcance del propio
        usuario o consulta puntual), este es un informe de RRHH fijo. El
        ALCANCE se decide aquí según el rol, NUNCA a partir de un parámetro
        del cliente (RGPD — un empleado no puede pedir el informe de otro
        usuario cambiando un query param):

        - administrador -> TODA la plantilla interna (`user_id=None`).
        - empleado -> SOLO sus propios fichajes (`user_id=current_user["sub"]`).

        El externo-invitado sigue rechazado por `require_role` (no tiene
        "Control horario" en la matriz de permisos)."""
        is_admin = current_user["role"] == RoleCode.ADMINISTRADOR
        scoped_user_id = None if is_admin else current_user["sub"]
        title = XLSX_TITLE_ADMIN if is_admin else XLSX_TITLE_EMPLOYEE

        today = today_in_madrid()
        date_from = today - timedelta(days=_DEFAULT_WINDOW_DAYS)
        rows = await use_case.execute(
            date_from=date_from, date_to=today, user_id=scoped_user_id
        )
        workbook_bytes = build_time_clock_export_workbook(
            rows, date_from=date_from, date_to=today, title=title
        )
        filename = f"fichajes-{today.isoformat()}.xlsx"
        return StreamingResponse(
            iter([workbook_bytes]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.patch("/entries/{entry_id}", response_model=TimeClockEntryDTO)
    async def update_entry(
        entry_id: str,
        dto: UpdateTimeClockEntryDTO,
        # `socio` [migración 024] = igual que empleado -> ficha su propio
        # horario como cualquier trabajador; solo `/entries/{id}/notes` (POST)
        # sigue exclusivo del admin (incidencia de RRHH, no del titular).
        current_user: dict = Depends(require_role(*TIME_CLOCK_ROLES)),
        use_case: UpdateTimeClockEntryUseCase = Depends(get_update_time_clock_entry_use_case),
    ):
        entry = await use_case.execute(
            entry_id=entry_id,
            requester_id=current_user["sub"],
            requester_role=current_user["role"],
            clock_in=dto.clock_in,
            clock_out=dto.clock_out,
        )
        return entry_to_dto(entry)

    @router.delete("/entries/{entry_id}", status_code=204)
    async def delete_entry(
        entry_id: str,
        # `socio` [migración 024] = igual que empleado -> ficha su propio
        # horario como cualquier trabajador; solo `/entries/{id}/notes` (POST)
        # sigue exclusivo del admin (incidencia de RRHH, no del titular).
        current_user: dict = Depends(require_role(*TIME_CLOCK_ROLES)),
        use_case: DeleteTimeClockEntryUseCase = Depends(get_delete_time_clock_entry_use_case),
    ):
        await use_case.execute(
            entry_id=entry_id,
            requester_id=current_user["sub"],
            requester_role=current_user["role"],
        )

    # --- Incidencias/comentarios sobre un tramo (B-2b) ---

    @router.post(
        "/entries/{entry_id}/notes", response_model=TimeClockEntryNoteDTO, status_code=201
    )
    async def add_entry_note(
        entry_id: str,
        dto: AddTimeClockEntryNoteDTO,
        current_user: dict = Depends(require_role(*ADMIN_ONLY)),
        use_case: AddTimeClockEntryNoteUseCase = Depends(get_add_time_clock_entry_note_use_case),
    ):
        """Solo el admin puede dejar incidencias sobre un tramo — no es una
        conversación bidireccional, es una anotación de RRHH
        (docs/permisos-roles.md § Control horario)."""
        note = await use_case.execute(
            entry_id=entry_id, author_id=current_user["sub"], body=dto.body
        )
        return note_to_dto(note)

    @router.get("/entries/{entry_id}/notes", response_model=TimeClockEntryNoteListDTO)
    async def list_entry_notes(
        entry_id: str,
        # `socio` [migración 024] = igual que empleado -> ficha su propio
        # horario como cualquier trabajador; solo `/entries/{id}/notes` (POST)
        # sigue exclusivo del admin (incidencia de RRHH, no del titular).
        current_user: dict = Depends(require_role(*TIME_CLOCK_ROLES)),
        use_case: ListTimeClockEntryNotesUseCase = Depends(get_list_time_clock_entry_notes_use_case),
    ):
        """El dueño del tramo puede leer sus propias incidencias; el admin,
        las de cualquiera — mismo alcance que editar/eliminar el tramo."""
        notes = await use_case.execute(
            entry_id=entry_id,
            requester_id=current_user["sub"],
            requester_role=current_user["role"],
        )
        return notes_to_dto(notes)

    # --- Fichaje en vivo (modelo "ambos" — complementa los tramos manuales
    # de arriba, no los sustituye; docs/deck-fase3/01-home-empleado.png).
    # Paths y forma de respuesta son el contrato acordado con el frontend
    # (`time-clock/domain/ports.ts`): las 4 acciones devuelven el MISMO
    # `TimeClockCurrentStatusDTO` que `GET /current`, ya recalculado tras el
    # cambio — evita que el frontend tenga que volver a pedirlo aparte. ---

    async def _current_status(
        user_id: str, status_use_case: GetLiveStatusUseCase
    ) -> TimeClockCurrentStatusDTO:
        status = await status_use_case.execute(user_id=user_id)
        return live_status_to_dto(status)

    @router.get("/current", response_model=TimeClockCurrentStatusDTO)
    async def get_current_status(
        # `socio` [migración 024] = igual que empleado -> ficha su propio
        # horario como cualquier trabajador; solo `/entries/{id}/notes` (POST)
        # sigue exclusivo del admin (incidencia de RRHH, no del titular).
        current_user: dict = Depends(require_role(*TIME_CLOCK_ROLES)),
        use_case: GetLiveStatusUseCase = Depends(get_live_status_use_case),
    ):
        return await _current_status(current_user["sub"], use_case)

    @router.post("/clock-in", response_model=TimeClockCurrentStatusDTO, status_code=201)
    async def clock_in(
        # `socio` [migración 024] = igual que empleado -> ficha su propio
        # horario como cualquier trabajador; solo `/entries/{id}/notes` (POST)
        # sigue exclusivo del admin (incidencia de RRHH, no del titular).
        current_user: dict = Depends(require_role(*TIME_CLOCK_ROLES)),
        use_case: ClockInUseCase = Depends(get_clock_in_use_case),
        status_use_case: GetLiveStatusUseCase = Depends(get_live_status_use_case),
    ):
        await use_case.execute(user_id=current_user["sub"])
        return await _current_status(current_user["sub"], status_use_case)

    @router.post("/clock-out", response_model=TimeClockCurrentStatusDTO)
    async def clock_out(
        # `socio` [migración 024] = igual que empleado -> ficha su propio
        # horario como cualquier trabajador; solo `/entries/{id}/notes` (POST)
        # sigue exclusivo del admin (incidencia de RRHH, no del titular).
        current_user: dict = Depends(require_role(*TIME_CLOCK_ROLES)),
        use_case: ClockOutUseCase = Depends(get_clock_out_use_case),
        status_use_case: GetLiveStatusUseCase = Depends(get_live_status_use_case),
    ):
        await use_case.execute(user_id=current_user["sub"])
        return await _current_status(current_user["sub"], status_use_case)

    @router.post("/breaks/start", response_model=TimeClockCurrentStatusDTO, status_code=201)
    async def start_break(
        # `socio` [migración 024] = igual que empleado -> ficha su propio
        # horario como cualquier trabajador; solo `/entries/{id}/notes` (POST)
        # sigue exclusivo del admin (incidencia de RRHH, no del titular).
        current_user: dict = Depends(require_role(*TIME_CLOCK_ROLES)),
        use_case: StartBreakUseCase = Depends(get_start_break_use_case),
        status_use_case: GetLiveStatusUseCase = Depends(get_live_status_use_case),
    ):
        await use_case.execute(user_id=current_user["sub"])
        return await _current_status(current_user["sub"], status_use_case)

    @router.post("/breaks/end", response_model=TimeClockCurrentStatusDTO)
    async def end_break(
        # `socio` [migración 024] = igual que empleado -> ficha su propio
        # horario como cualquier trabajador; solo `/entries/{id}/notes` (POST)
        # sigue exclusivo del admin (incidencia de RRHH, no del titular).
        current_user: dict = Depends(require_role(*TIME_CLOCK_ROLES)),
        use_case: EndBreakUseCase = Depends(get_end_break_use_case),
        status_use_case: GetLiveStatusUseCase = Depends(get_live_status_use_case),
    ):
        await use_case.execute(user_id=current_user["sub"])
        return await _current_status(current_user["sub"], status_use_case)

    # --- Parte diario del técnico (requerimiento v1.2 §M1) ---
    #
    # Guard propio: `TECHNICIAN_ROLES + ADMIN_ONLY`, NO `TIME_CLOCK_ROLES`.
    # El técnico no ficha por tramos y el empleado no cumplimenta partes: son
    # dos módulos distintos sobre la misma tabla, y copiar el `Depends` del
    # vecino le daría a cada uno el del otro.

    @router.post("/technician-logs", response_model=TechnicianDailyLogDTO, status_code=201)
    async def create_technician_log(
        dto: TechnicianDailyLogInputDTO,
        current_user: dict = Depends(require_role(*TECHNICIAN_ROLES)),
        use_case: CreateTechnicianDailyLogUseCase = Depends(
            get_create_technician_daily_log_use_case
        ),
    ):
        """Cumplimenta el parte del día — siempre para el propio técnico
        autenticado: nadie rellena el parte de otro. El administrador corrige
        (PATCH) y consulta, pero no crea partes ajenos."""
        log = await use_case.execute(
            user_id=current_user["sub"],
            work_date=dto.work_date,
            started_at=dto.started_at,
            ended_at=dto.ended_at,
            project_id=dto.project_id,
            work_location=dto.work_location,
            had_break=dto.had_break,
            break_minutes=dto.break_minutes,
            overnight_stay=OvernightStay(dto.overnight_stay),
            product_category=ProductCategory(dto.product_category),
        )
        return daily_log_to_dto(log)

    @router.get("/technician-logs", response_model=TechnicianDailyLogListDTO)
    async def list_technician_logs(
        year: int = Query(..., ge=2020, le=2100),
        month: int = Query(..., ge=1, le=12),
        user_id: Optional[str] = Query(
            None, description="Solo el admin puede consultar a otro técnico"
        ),
        current_user: dict = Depends(require_role(*TECHNICIAN_ROLES, *ADMIN_ONLY)),
        use_case: ListTechnicianDailyLogsUseCase = Depends(
            get_list_technician_daily_logs_use_case
        ),
    ):
        """Partes de un mes natural más su resumen (consumo, excedente,
        compensación y pernoctas). El guard RGPD vive en el caso de uso."""
        logs, summary = await use_case.execute(
            requester_id=current_user["sub"],
            requester_role=current_user["role"],
            year=year,
            month=month,
            user_id=user_id,
        )
        return daily_logs_to_dto(logs, summary)

    # Declarada ANTES que las rutas con `{entry_id}`: FastAPI resuelve por
    # orden, y el día que alguien añada un `GET /technician-logs/{entry_id}`,
    # "balance" se colaría como identificador si estuviera declarada después.
    @router.get("/technician-logs/balance", response_model=CompensationBalanceDTO)
    async def get_compensation_balance(
        year: int = Query(..., ge=2020, le=2100),
        user_id: Optional[str] = Query(
            None, description="Solo el admin puede consultar a otro técnico"
        ),
        current_user: dict = Depends(require_role(*TECHNICIAN_ROLES, *ADMIN_ONLY)),
        use_case: GetCompensationBalanceUseCase = Depends(get_compensation_balance_use_case),
    ):
        """Saldo ANUAL de descanso por horas extra. Se calcula al vuelo: no hay
        tabla de saldos ni cierre de mes."""
        target_user_id = user_id or current_user["sub"]
        if current_user["role"] != RoleCode.ADMINISTRADOR and target_user_id != current_user["sub"]:
            raise TimeClockForbiddenError("Solo puedes consultar tu propio saldo.")
        balance = await use_case.execute(user_id=target_user_id, year=year)
        return compensation_balance_to_dto(balance)

    @router.get("/technician-logs/projects", response_model=ProjectListDTO)
    async def list_projects(
        _: dict = Depends(require_role(*TECHNICIAN_ROLES, *ADMIN_ONLY)),
        use_case: ListProjectsUseCase = Depends(get_list_projects_use_case),
    ):
        """Catálogo para el desplegable «Proyecto» del parte. Solo los activos:
        un proyecto cerrado sigue en la tabla porque los partes históricos lo
        referencian, pero no debe ofrecerse para jornadas nuevas."""
        return projects_to_dto(await use_case.execute())

    @router.get("/technician-logs/export.xlsx")
    async def export_technician_month(
        year: int = Query(..., ge=2020, le=2100),
        month: int = Query(..., ge=1, le=12),
        user_id: Optional[str] = Query(
            None, description="Solo el admin puede exportar el de otro técnico"
        ),
        current_user: dict = Depends(require_role(*TECHNICIAN_ROLES, *ADMIN_ONLY)),
        use_case: ListTechnicianDailyLogsUseCase = Depends(
            get_list_technician_daily_logs_use_case
        ),
    ):
        """Resumen mensual en Excel: hoja «Detalle» con todos los partes y hoja
        «Resumen» con horas extra, el ×1,45 como fórmula viva y los totales de
        pernocta dentro y fuera de España."""
        logs, summary = await use_case.execute(
            requester_id=current_user["sub"],
            requester_role=current_user["role"],
            year=year,
            month=month,
            user_id=user_id,
        )
        # El nombre sale de los propios partes; si el mes está vacío no hay a
        # quién nombrar y se cae al del solicitante.
        technician_name = next(
            (log.full_name for log in logs if log.full_name), current_user.get("name", "tecnico")
        )
        content = build_technician_month_workbook(
            logs, summary, technician_name=technician_name
        )
        filename = month_filename(summary, technician_name)
        return StreamingResponse(
            io.BytesIO(content),
            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.patch("/technician-logs/{entry_id}", response_model=TechnicianDailyLogDTO)
    async def update_technician_log(
        entry_id: str,
        dto: UpdateTechnicianDailyLogDTO,
        current_user: dict = Depends(require_role(*TECHNICIAN_ROLES, *ADMIN_ONLY)),
        use_case: UpdateTechnicianDailyLogUseCase = Depends(
            get_update_technician_daily_log_use_case
        ),
    ):
        """`work_date` del body se IGNORA: la fecha del parte no se edita,
        porque movería la jornada de mes y con ella el cómputo de la bolsa."""
        log = await use_case.execute(
            entry_id=entry_id,
            requester_id=current_user["sub"],
            requester_role=current_user["role"],
            started_at=dto.started_at,
            ended_at=dto.ended_at,
            project_id=dto.project_id,
            work_location=dto.work_location,
            had_break=dto.had_break,
            break_minutes=dto.break_minutes,
            overnight_stay=OvernightStay(dto.overnight_stay),
            product_category=ProductCategory(dto.product_category),
        )
        return daily_log_to_dto(log)

    @router.delete("/technician-logs/{entry_id}", status_code=204)
    async def delete_technician_log(
        entry_id: str,
        current_user: dict = Depends(require_role(*TECHNICIAN_ROLES, *ADMIN_ONLY)),
        use_case: DeleteTechnicianDailyLogUseCase = Depends(
            get_delete_technician_daily_log_use_case
        ),
    ):
        await use_case.execute(
            entry_id=entry_id,
            requester_id=current_user["sub"],
            requester_role=current_user["role"],
        )

    return router
