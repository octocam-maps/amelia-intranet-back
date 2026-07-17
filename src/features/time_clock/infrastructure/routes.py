"""Router de `/time-clock`: fichaje por tramos manuales, historial y export CSV."""

import csv
import io
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from src.shared.auth.dependencies import require_role
from src.shared.utils.timezone import today_in_madrid

from ..application.use_cases.add_time_clock_entry_note import AddTimeClockEntryNoteUseCase
from ..application.use_cases.clock_in import ClockInUseCase
from ..application.use_cases.clock_out import ClockOutUseCase
from ..application.use_cases.create_time_clock_entry import CreateTimeClockEntryUseCase
from ..application.use_cases.delete_time_clock_entry import DeleteTimeClockEntryUseCase
from ..application.use_cases.end_break import EndBreakUseCase
from ..application.use_cases.export_time_clock_entries import ExportTimeClockEntriesUseCase
from ..application.use_cases.get_live_status import GetLiveStatusUseCase
from ..application.use_cases.list_time_clock_entries import ListTimeClockEntriesUseCase
from ..application.use_cases.list_time_clock_entry_notes import ListTimeClockEntryNotesUseCase
from ..application.use_cases.start_break import StartBreakUseCase
from ..application.use_cases.update_time_clock_entry import UpdateTimeClockEntryUseCase
from .dependencies import (
    get_add_time_clock_entry_note_use_case,
    get_clock_in_use_case,
    get_clock_out_use_case,
    get_create_time_clock_entry_use_case,
    get_delete_time_clock_entry_use_case,
    get_end_break_use_case,
    get_export_time_clock_entries_use_case,
    get_list_time_clock_entries_use_case,
    get_list_time_clock_entry_notes_use_case,
    get_live_status_use_case,
    get_start_break_use_case,
    get_update_time_clock_entry_use_case,
)
from .mappers import entries_to_dto, entry_to_dto, live_status_to_dto, note_to_dto, notes_to_dto
from .schemas import (
    AddTimeClockEntryNoteDTO,
    CreateTimeClockEntryDTO,
    TimeClockCurrentStatusDTO,
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
    @router.post("/entries", response_model=TimeClockEntryDTO, status_code=201)
    async def create_entry(
        dto: CreateTimeClockEntryDTO,
        # `socio` [migración 024] = igual que empleado -> ficha su propio
        # horario como cualquier trabajador; solo `/entries/{id}/notes` (POST)
        # sigue exclusivo del admin (incidencia de RRHH, no del titular).
        current_user: dict = Depends(require_role("administrador", "empleado", "socio")),
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
        current_user: dict = Depends(require_role("administrador", "empleado", "socio")),
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
        current_user: dict = Depends(require_role("administrador", "empleado", "socio")),
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
        current_user: dict = Depends(require_role("administrador", "empleado", "socio")),
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
        is_admin = current_user["role"] == "administrador"
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
        current_user: dict = Depends(require_role("administrador", "empleado", "socio")),
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
        current_user: dict = Depends(require_role("administrador", "empleado", "socio")),
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
        current_user: dict = Depends(require_role("administrador")),
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
        current_user: dict = Depends(require_role("administrador", "empleado", "socio")),
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
        current_user: dict = Depends(require_role("administrador", "empleado", "socio")),
        use_case: GetLiveStatusUseCase = Depends(get_live_status_use_case),
    ):
        return await _current_status(current_user["sub"], use_case)

    @router.post("/clock-in", response_model=TimeClockCurrentStatusDTO, status_code=201)
    async def clock_in(
        # `socio` [migración 024] = igual que empleado -> ficha su propio
        # horario como cualquier trabajador; solo `/entries/{id}/notes` (POST)
        # sigue exclusivo del admin (incidencia de RRHH, no del titular).
        current_user: dict = Depends(require_role("administrador", "empleado", "socio")),
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
        current_user: dict = Depends(require_role("administrador", "empleado", "socio")),
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
        current_user: dict = Depends(require_role("administrador", "empleado", "socio")),
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
        current_user: dict = Depends(require_role("administrador", "empleado", "socio")),
        use_case: EndBreakUseCase = Depends(get_end_break_use_case),
        status_use_case: GetLiveStatusUseCase = Depends(get_live_status_use_case),
    ):
        await use_case.execute(user_id=current_user["sub"])
        return await _current_status(current_user["sub"], status_use_case)

    return router
