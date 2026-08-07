"""
Caso de uso: cumplimentar el parte diario del técnico (requerimiento v1.2
§M1). Reglas de negocio:

- UN parte por técnico y día. `uq_technician_daily_logs_one_per_day` es la red
  de seguridad; aquí se comprueba antes solo para dar un mensaje legible.
- La jornada SÍ puede cruzar la medianoche (de 08:00 a 01:30 del día
  siguiente). Es la diferencia principal con `CreateTimeClockEntryUseCase`,
  que lo prohíbe: el técnico de campo vuelve al hotel cuando vuelve, y un
  registro que no puede contarlo obliga a mentir en el parte.
- Se imputa al `work_date` en que EMPIEZA la jornada, no al de la llegada.
- LOGIC-2 (pentest ético, severidad ALTA): `work_date` no puede ser futura ni
  más antigua que `manual_entry_max_past_days`. Misma ventana y mismo motivo
  que el alta manual — el parte también es autodeclarado.
- `worked_minutes` NUNCA se acepta del cliente: se calcula. Confiar en el
  número que llega en el body permitiría declarar 4 horas en una jornada de 12
  o al revés, y es justo el dato del que cuelga toda la bolsa de horas.
"""

from datetime import date, datetime, timedelta

from src.shared.utils.timezone import MADRID_TZ, today_in_madrid

from ...domain.entities import (
    OvernightStay,
    ProductCategory,
    TechnicianDailyLog,
)
from ...domain.errors import (
    DuplicateDailyLogError,
    InvalidBreakError,
    InvalidTimeRangeError,
    ManualEntryOutOfWindowError,
    ProjectNotFoundError,
    TimeClockOverlapError,
)
from ...domain.ports import ITimeClockRepository

# Tope de duración bruta de una jornada. No es una regla laboral —el art. 34.3
# ET habla de 9 h ordinarias, y este parte admite jornadas atípicas más largas
# a propósito— sino un cortafuegos contra el error de tecleo: sin él, una
# llegada mal escrita puede meter 200 horas en la bolsa del mes.
MAX_GROSS_MINUTES = 24 * 60


class CreateTechnicianDailyLogUseCase:
    def __init__(
        self, repository: ITimeClockRepository, manual_entry_max_past_days: int
    ):
        self._repository = repository
        self._manual_entry_max_past_days = manual_entry_max_past_days

    async def execute(
        self,
        *,
        user_id: str,
        work_date: date,
        started_at: datetime,
        ended_at: datetime,
        project_id: str,
        work_location: str,
        had_break: bool,
        break_minutes: int,
        overnight_stay: OvernightStay,
        product_category: ProductCategory,
    ) -> TechnicianDailyLog:
        validate_daily_log_range(work_date, started_at, ended_at, break_minutes)
        validate_break(had_break, break_minutes)
        self._validate_window(work_date)

        project = await self._repository.find_project(project_id)
        if project is None or not project.is_active:
            raise ProjectNotFoundError(
                "El proyecto indicado no existe o está desactivado."
            )

        existing = await self._repository.find_daily_log_for_date(user_id, work_date)
        if existing is not None:
            raise DuplicateDailyLogError(
                "Ya existe un parte para ese día. Edítalo en lugar de crear otro."
            )

        overlapping = await self._repository.find_overlapping_entry(
            user_id, work_date, started_at, ended_at
        )
        if overlapping is not None:
            raise TimeClockOverlapError(
                "Ese horario se solapa con otra jornada ya registrada."
            )

        return await self._repository.create_daily_log(
            user_id=user_id,
            work_date=work_date,
            started_at=started_at,
            ended_at=ended_at,
            project_id=project_id,
            work_location=work_location.strip(),
            had_break=had_break,
            break_minutes=break_minutes,
            overnight_stay=overnight_stay,
            product_category=product_category,
        )

    def _validate_window(self, work_date: date) -> None:
        today = today_in_madrid()
        if work_date > today:
            raise ManualEntryOutOfWindowError(
                "No puedes registrar un tramo con fecha futura."
            )
        oldest_allowed = today - timedelta(days=self._manual_entry_max_past_days)
        if work_date < oldest_allowed:
            raise ManualEntryOutOfWindowError(
                "No puedes registrar un tramo de hace más de "
                f"{self._manual_entry_max_past_days} días."
            )


def validate_daily_log_range(
    work_date: date, started_at: datetime, ended_at: datetime, break_minutes: int
) -> None:
    """Compartida por el alta y la edición.

    A diferencia de `create_time_clock_entry._validate_range`, aquí NO se exige
    que la salida caiga en el mismo día: solo que la ENTRADA lo haga. Es lo que
    permite la jornada que cruza la medianoche.
    """
    # La fecha se compara en hora de MADRID, no en la del datetime recibido.
    # El navegador manda el instante en UTC (`Date.toISOString()`), así que una
    # jornada que empieza a las 00:30 de Madrid llega como las 23:30 del día
    # ANTERIOR: comparar `started_at.date()` en crudo rechazaba como "fuera de
    # fecha" justo el turno que este parte existe para poder registrar. Con
    # `today_in_madrid()` ya se usa el mismo huso para la ventana temporal, así
    # que aquí sería incoherente usar otro.
    if started_at.astimezone(MADRID_TZ).date() != work_date:
        raise InvalidTimeRangeError(
            "La hora de inicio debe caer dentro de la fecha del parte."
        )
    if ended_at <= started_at:
        raise InvalidTimeRangeError("La hora de fin debe ser posterior a la de inicio.")

    gross_minutes = int((ended_at - started_at).total_seconds() // 60)
    if gross_minutes > MAX_GROSS_MINUTES:
        raise InvalidTimeRangeError("Una jornada no puede durar más de 24 horas.")
    if break_minutes >= gross_minutes:
        raise InvalidBreakError("La pausa no puede superar la duración de la jornada.")


def validate_break(had_break: bool, break_minutes: int) -> None:
    """`had_break` es un dato DECLARADO, no derivado de `break_minutes > 0`:
    "no hubo pausa" y "hubo pausa de 0 minutos" son afirmaciones distintas ante
    una inspección. Lo que no puede es contradecirse a sí mismo."""
    if break_minutes < 0:
        raise InvalidBreakError("El tiempo de pausa no puede ser negativo.")
    if not had_break and break_minutes > 0:
        raise InvalidBreakError(
            f"Has marcado que no hubo pausa pero has informado {break_minutes} minutos."
        )
    if had_break and break_minutes == 0:
        raise InvalidBreakError("Has marcado que hubo pausa: indica cuántos minutos.")
