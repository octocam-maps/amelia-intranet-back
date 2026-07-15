"""Router de `/team`: directorio y calendario de vacaciones. Visible para
los 3 roles (docs/permisos-roles.md § Equipo) — solo lectura."""

from fastapi import APIRouter, Depends, Query

from src.shared.auth.dependencies import require_role

from ..application.use_cases.get_team_calendar import GetTeamCalendarUseCase
from ..application.use_cases.get_upcoming_birthdays import GetUpcomingBirthdaysUseCase
from ..application.use_cases.list_team_directory import ListTeamDirectoryUseCase
from .dependencies import (
    get_list_team_directory_use_case,
    get_team_calendar_use_case,
    get_upcoming_birthdays_use_case,
)
from .mappers import birthdays_to_dto, directory_to_dto, team_calendar_to_dto
from .schemas import TeamAbsenceCalendarDTO, TeamBirthdaysDTO, TeamDirectoryDTO

_ALL_ROLES = ("administrador", "empleado", "externo_invitado")


def create_team_router() -> APIRouter:
    router = APIRouter(prefix="/team", tags=["team"])

    @router.get("/directory", response_model=TeamDirectoryDTO)
    async def get_directory(
        current_user: dict = Depends(require_role(*_ALL_ROLES)),
        use_case: ListTeamDirectoryUseCase = Depends(get_list_team_directory_use_case),
    ):
        """Directorio de la plantilla — campos seguros de cara al RGPD,
        nunca datos sensibles de `user_profiles` (dni_nif/iban/etc.)."""
        members = await use_case.execute()
        return directory_to_dto(members)

    @router.get("/vacation-calendar", response_model=TeamAbsenceCalendarDTO)
    async def get_vacation_calendar(
        month: str = Query(
            ...,
            pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
            description="Mes en formato YYYY-MM",
        ),
        current_user: dict = Depends(require_role(*_ALL_ROLES)),
        use_case: GetTeamCalendarUseCase = Depends(get_team_calendar_use_case),
    ):
        """Ausencias ya APROBADAS de los compañeros del MISMO departamento
        que el solicitante (`current_user["sub"]`, resuelto en backend) —
        nunca de toda la plantilla ni de otro departamento, y nunca
        solicitudes pendientes/rechazadas. Cada entrada expone un `kind`
        privacy-safe (`vacaciones`/`remoto`/`ausente`), nunca el tipo real
        de ausencia (RGPD: baja médica/duelo/etc. son datos sensibles)."""
        year, month_number = (int(part) for part in month.split("-"))
        entries = await use_case.execute(
            requester_id=current_user["sub"], year=year, month=month_number
        )
        return team_calendar_to_dto(entries)

    @router.get("/birthdays", response_model=TeamBirthdaysDTO)
    async def get_birthdays(
        days: int = Query(
            7,
            ge=1,
            le=366,
            description="Tamaño de la ventana en días, incluyendo hoy (por defecto 7)",
        ),
        current_user: dict = Depends(require_role(*_ALL_ROLES)),
        use_case: GetUpcomingBirthdaysUseCase = Depends(get_upcoming_birthdays_use_case),
    ):
        """Cumpleaños de la plantilla interna dentro de la ventana `days`
        (widget "Cumpleaños esta semana" del Inicio) — nunca externos, y
        comparando solo mes-día del nacimiento, ignorando el año."""
        birthdays = await use_case.execute(days=days)
        return birthdays_to_dto(birthdays)

    return router
