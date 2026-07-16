"""
Router de `/holidays`: calendario laboral (docs/permisos-roles.md §
"Festivos" — el admin los marca anualmente, el resto de la plantilla los
consulta en su calendario de ausencias). El externo-invitado no tiene
"Ausencias" en la matriz de permisos (❌) — se rechaza aquí, en el backend.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.shared.auth.dependencies import require_role

from ..application.use_cases.create_holiday import CreateHolidayUseCase
from ..application.use_cases.delete_holiday import DeleteHolidayUseCase
from ..application.use_cases.import_official_holidays import (
    ImportOfficialHolidaysUseCase,
)
from ..application.use_cases.list_holidays import ListHolidaysUseCase
from ..application.use_cases.update_holiday import UpdateHolidayUseCase
from ..domain.errors import HolidayProviderError
from .dependencies import (
    get_create_holiday_use_case,
    get_delete_holiday_use_case,
    get_import_official_holidays_use_case,
    get_list_holidays_use_case,
    get_update_holiday_use_case,
)
from .mappers import holiday_to_dto, holidays_to_dto
from .schemas import (
    CreateHolidayDTO,
    HolidayDTO,
    HolidayImportResultDTO,
    HolidayListDTO,
    UpdateHolidayDTO,
)


def create_holidays_router() -> APIRouter:
    router = APIRouter(prefix="/holidays", tags=["holidays"])

    @router.get("", response_model=HolidayListDTO)
    async def list_holidays(
        year: Optional[int] = Query(None),
        entity: Optional[str] = Query(None, description="Filtra por código de entidad (hub/lab/ops)"),
        # `socio` [migración 024] = igual que empleado -> consulta el
        # calendario laboral, sigue sin poder marcar/editar festivos.
        current_user: dict = Depends(require_role("administrador", "empleado", "socio")),
        use_case: ListHolidaysUseCase = Depends(get_list_holidays_use_case),
    ):
        holidays = await use_case.execute(year=year, entity_code=entity)
        return holidays_to_dto(holidays)

    @router.post("", response_model=HolidayDTO, status_code=201)
    async def create_holiday(
        dto: CreateHolidayDTO,
        current_user: dict = Depends(require_role("administrador")),
        use_case: CreateHolidayUseCase = Depends(get_create_holiday_use_case),
    ):
        holiday = await use_case.execute(
            day=dto.day, name=dto.name, entity_code=dto.entity, scope=dto.scope
        )
        return holiday_to_dto(holiday)

    @router.post("/import", response_model=HolidayImportResultDTO)
    async def import_official_holidays(
        year: Optional[int] = Query(
            None, description="Año a importar; por defecto el año en curso."
        ),
        current_user: dict = Depends(require_role("administrador")),
        use_case: ImportOfficialHolidaysUseCase = Depends(
            get_import_official_holidays_use_case
        ),
    ):
        target_year = year or datetime.now(timezone.utc).year
        try:
            summary = await use_case.execute(year=target_year)
        except HolidayProviderError as exc:
            # Fallo de dependencia externa (Nager.Date) -> 502, no 500 ni 4xx.
            raise HTTPException(status_code=502, detail=exc.message) from exc
        return HolidayImportResultDTO(
            year=target_year,
            imported=summary.imported,
            updated=summary.updated,
            skipped=summary.skipped,
        )

    @router.patch("/{holiday_id}", response_model=HolidayDTO)
    async def update_holiday(
        holiday_id: str,
        dto: UpdateHolidayDTO,
        current_user: dict = Depends(require_role("administrador")),
        use_case: UpdateHolidayUseCase = Depends(get_update_holiday_use_case),
    ):
        # `model_fields_set` distingue "el cliente no mandó `entity`" (no
        # tocar el ámbito) de "mandó `entity: null`" (vaciarlo -> aplica a
        # las 3 entidades) — un `Optional[str] = None` por sí solo no puede.
        kwargs = {"day": dto.day, "name": dto.name, "scope": dto.scope}
        if "entity" in dto.model_fields_set:
            kwargs["entity_code"] = dto.entity
        holiday = await use_case.execute(holiday_id, **kwargs)
        return holiday_to_dto(holiday)

    @router.delete("/{holiday_id}", status_code=204)
    async def delete_holiday(
        holiday_id: str,
        current_user: dict = Depends(require_role("administrador")),
        use_case: DeleteHolidayUseCase = Depends(get_delete_holiday_use_case),
    ):
        await use_case.execute(holiday_id)

    return router
