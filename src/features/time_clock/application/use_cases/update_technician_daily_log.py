"""
Caso de uso: corregir un parte diario ya registrado.

`work_date` no se puede cambiar: movería el parte de mes y con él el cómputo
de la bolsa de 162 h y el saldo de compensación ya devengado. Para eso se
borra el parte y se crea de nuevo en la fecha correcta, que además deja el
rastro de las dos operaciones en vez de un cambio silencioso.

Alcance: el técnico corrige los suyos; el administrador, los de cualquiera
(docs/permisos-roles.md § Control horario). El filtrado va aquí, en el
backend, nunca en la UI.
"""

from src.shared.auth.roles import RoleCode

from ...domain.entities import OvernightStay, ProductCategory, TechnicianDailyLog
from ...domain.errors import (
    ProjectNotFoundError,
    TechnicianDailyLogNotFoundError,
    TimeClockForbiddenError,
    TimeClockOverlapError,
)
from ...domain.ports import ITimeClockRepository
from .create_technician_daily_log import validate_break, validate_daily_log_range


class UpdateTechnicianDailyLogUseCase:
    def __init__(self, repository: ITimeClockRepository):
        self._repository = repository

    async def execute(
        self,
        *,
        entry_id: str,
        requester_id: str,
        requester_role: str,
        started_at,
        ended_at,
        project_id: str,
        work_location: str,
        had_break: bool,
        break_minutes: int,
        overnight_stay: OvernightStay,
        product_category: ProductCategory,
    ) -> TechnicianDailyLog:
        existing = await self._repository.find_daily_log(entry_id)
        if existing is None:
            raise TechnicianDailyLogNotFoundError(
                "No existe un parte con ese identificador."
            )

        if (
            requester_role != RoleCode.ADMINISTRADOR
            and existing.user_id != requester_id
        ):
            raise TimeClockForbiddenError("Solo puedes editar tus propios partes.")

        validate_daily_log_range(
            existing.work_date, started_at, ended_at, break_minutes
        )
        validate_break(had_break, break_minutes)

        project = await self._repository.find_project(project_id)
        if project is None or not project.is_active:
            raise ProjectNotFoundError(
                "El proyecto indicado no existe o está desactivado."
            )

        # `exclude_entry_id` para no compararlo consigo mismo: sin esto,
        # guardar un parte sin tocarle las horas se rechazaría por solaparse
        # con su propia versión almacenada.
        overlapping = await self._repository.find_overlapping_entry(
            existing.user_id,
            existing.work_date,
            started_at,
            ended_at,
            exclude_entry_id=entry_id,
        )
        if overlapping is not None:
            raise TimeClockOverlapError(
                "Ese horario se solapa con otra jornada ya registrada."
            )

        return await self._repository.update_daily_log(
            entry_id,
            started_at=started_at,
            ended_at=ended_at,
            project_id=project_id,
            work_location=work_location.strip(),
            had_break=had_break,
            break_minutes=break_minutes,
            overnight_stay=overnight_stay,
            product_category=product_category,
        )
