"""Router de `/time-clock`: fichaje por tramos manuales, historial y export CSV."""

import csv
import io
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from src.shared.auth.dependencies import require_role
from src.shared.utils.timezone import today_in_madrid

from ..application.use_cases.clock_in import ClockInUseCase
from ..application.use_cases.clock_out import ClockOutUseCase
from ..application.use_cases.create_time_clock_entry import CreateTimeClockEntryUseCase
from ..application.use_cases.delete_time_clock_entry import DeleteTimeClockEntryUseCase
from ..application.use_cases.end_break import EndBreakUseCase
from ..application.use_cases.get_live_status import GetLiveStatusUseCase
from ..application.use_cases.list_time_clock_entries import ListTimeClockEntriesUseCase
from ..application.use_cases.start_break import StartBreakUseCase
from ..application.use_cases.update_time_clock_entry import UpdateTimeClockEntryUseCase
from .dependencies import (
    get_clock_in_use_case,
    get_clock_out_use_case,
    get_create_time_clock_entry_use_case,
    get_delete_time_clock_entry_use_case,
    get_end_break_use_case,
    get_list_time_clock_entries_use_case,
    get_live_status_use_case,
    get_start_break_use_case,
    get_update_time_clock_entry_use_case,
)
from .mappers import break_to_dto, entries_to_dto, entry_to_dto, live_status_to_dto
from .schemas import (
    CreateTimeClockEntryDTO,
    LiveClockStatusDTO,
    TimeClockBreakDTO,
    TimeClockEntryDTO,
    TimeClockEntryListDTO,
    UpdateTimeClockEntryDTO,
)

_DEFAULT_WINDOW_DAYS = 30


def _resolve_range(date_from: Optional[date], date_to: Optional[date]) -> tuple[date, date]:
    # TZ-1: "hoy" del historial y del export es Europe/Madrid, no la TZ del
    # proceso (UTC) — evita que el último tramo del día "se pierda" de la
    # ventana por defecto justo alrededor de la medianoche.
    today = today_in_madrid()
    return date_from or (today - timedelta(days=_DEFAULT_WINDOW_DAYS)), date_to or today


def create_time_clock_router() -> APIRouter:
    router = APIRouter(prefix="/time-clock", tags=["time-clock"])

    # El externo-invitado no tiene "Control horario" en la matriz de permisos
    # (docs/permisos-roles.md: ❌) — se rechaza aquí, en el backend, no solo
    # ocultando el ítem del navbar.
    @router.post("/entries", response_model=TimeClockEntryDTO, status_code=201)
    async def create_entry(
        dto: CreateTimeClockEntryDTO,
        current_user: dict = Depends(require_role("administrador", "empleado")),
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
        date_from: Optional[date] = Query(None),
        date_to: Optional[date] = Query(None),
        current_user: dict = Depends(require_role("administrador", "empleado")),
        use_case: ListTimeClockEntriesUseCase = Depends(get_list_time_clock_entries_use_case),
    ):
        """Historial de tramos. Sin `user_id`: los propios (TODOS si el rol es admin)."""
        resolved_from, resolved_to = _resolve_range(date_from, date_to)
        entries = await use_case.execute(
            requester_id=current_user["sub"],
            requester_role=current_user["role"],
            target_user_id=user_id,
            date_from=resolved_from,
            date_to=resolved_to,
        )
        return entries_to_dto(entries)

    @router.get("/entries/export")
    async def export_entries(
        user_id: Optional[str] = Query(None),
        date_from: Optional[date] = Query(None),
        date_to: Optional[date] = Query(None),
        current_user: dict = Depends(require_role("administrador", "empleado")),
        use_case: ListTimeClockEntriesUseCase = Depends(get_list_time_clock_entries_use_case),
    ):
        """Exportación básica en CSV del mismo listado de `GET /time-clock/entries`."""
        resolved_from, resolved_to = _resolve_range(date_from, date_to)
        entries = await use_case.execute(
            requester_id=current_user["sub"],
            requester_role=current_user["role"],
            target_user_id=user_id,
            date_from=resolved_from,
            date_to=resolved_to,
        )

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["fecha", "entrada", "salida", "minutos_trabajados", "origen"])
        for entry in entries:
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

    @router.patch("/entries/{entry_id}", response_model=TimeClockEntryDTO)
    async def update_entry(
        entry_id: str,
        dto: UpdateTimeClockEntryDTO,
        current_user: dict = Depends(require_role("administrador", "empleado")),
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
        current_user: dict = Depends(require_role("administrador", "empleado")),
        use_case: DeleteTimeClockEntryUseCase = Depends(get_delete_time_clock_entry_use_case),
    ):
        await use_case.execute(
            entry_id=entry_id,
            requester_id=current_user["sub"],
            requester_role=current_user["role"],
        )

    # --- Fichaje en vivo (modelo "ambos" — complementa los tramos manuales
    # de arriba, no los sustituye; docs/deck-fase3/01-home-empleado.png) ---

    @router.get("/live/status", response_model=LiveClockStatusDTO)
    async def get_live_status(
        current_user: dict = Depends(require_role("administrador", "empleado")),
        use_case: GetLiveStatusUseCase = Depends(get_live_status_use_case),
    ):
        status = await use_case.execute(user_id=current_user["sub"])
        return live_status_to_dto(status)

    @router.post("/live/clock-in", response_model=TimeClockEntryDTO, status_code=201)
    async def clock_in(
        current_user: dict = Depends(require_role("administrador", "empleado")),
        use_case: ClockInUseCase = Depends(get_clock_in_use_case),
    ):
        entry = await use_case.execute(user_id=current_user["sub"])
        return entry_to_dto(entry)

    @router.post("/live/clock-out", response_model=TimeClockEntryDTO)
    async def clock_out(
        current_user: dict = Depends(require_role("administrador", "empleado")),
        use_case: ClockOutUseCase = Depends(get_clock_out_use_case),
    ):
        entry = await use_case.execute(user_id=current_user["sub"])
        return entry_to_dto(entry)

    @router.post("/live/breaks/start", response_model=TimeClockBreakDTO, status_code=201)
    async def start_break(
        current_user: dict = Depends(require_role("administrador", "empleado")),
        use_case: StartBreakUseCase = Depends(get_start_break_use_case),
    ):
        break_ = await use_case.execute(user_id=current_user["sub"])
        return break_to_dto(break_)

    @router.post("/live/breaks/end", response_model=TimeClockBreakDTO)
    async def end_break(
        current_user: dict = Depends(require_role("administrador", "empleado")),
        use_case: EndBreakUseCase = Depends(get_end_break_use_case),
    ):
        break_ = await use_case.execute(user_id=current_user["sub"])
        return break_to_dto(break_)

    return router
