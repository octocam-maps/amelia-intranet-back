"""
Caso de uso: alta de fichaje en lote sobre un rango de días (RF-A3).

## Orden de evaluación día-a-día — el punto crítico (LOGIC-2, pentest ético,
severidad ALTA)

Dos familias de reglas, evaluadas en este orden estricto por día, PRIMER
MATCH GANA:

1. Filtros de calendario (producen OMISIÓN con motivo, nunca tumban el
   lote): `fin_de_semana` -> `festivo` (escopado por entidad) -> `ausencia`
   (aprobada, propia) -> `ya_registrado`.
2. Violaciones de política (evaluadas SOLO sobre los días que sobrevivieron
   al paso 1):
   - `fuera_de_ventana` (más de `manual_entry_max_past_days` en el pasado)
     -> OMISIÓN, no tumba el lote.
   - `futuro` (`work_date > hoy` Europe/Madrid) -> RECHAZA TODO EL LOTE
     (422), en DOS PASADAS conceptuales: la clasificación entera se hace
     ANTES de escribir nada en BD; en cuanto un día llega a "futuro" se
     aborta sin crear ni un solo tramo (ni los días pasados válidos del
     mismo lote).

Por qué este orden importa (NO cambiarlo): el caso de uso real es fichar la
semana en curso un viernes, seleccionando lunes->domingo. Sábado y domingo
son futuros, pero se omiten por `fin_de_semana` ANTES de llegar al chequeo
de futuro, así que el lote se acepta — un fin de semana NUNCA genera un
tramo, cero riesgo de seguridad. En cambio un día laborable futuro SIN
ninguna exclusión de calendario que lo cubra SÍ habría generado un tramo
con fecha futura -- eso es exactamente lo que LOGIC-2 cerró, así que tumba
el lote entero. El filtro de calendario nunca "salva" a un día laborable
futuro sin exclusión propia: solo protege a los días que de todos modos
iban a omitirse.

Cada día que sobrevive ambos pasos se delega en
`CreateTimeClockEntryUseCase.execute()` — reutiliza al 100% las
validaciones de solape, no-cruza-medianoche y `source=manual` forzado por
backend, cero duplicación de esa lógica.
"""

from datetime import date, datetime, time, timedelta

from src.shared.utils.timezone import MADRID_TZ, today_in_madrid

from ...domain.entities import TimeClockBatchOmissionReason
from ...domain.errors import (
    TimeClockBatchDateRangeInvertedError,
    TimeClockBatchFutureDateError,
    TimeClockBatchRangeTooLongError,
)
from ...domain.ports import ITimeClockRepository
from ..results import OmittedBatchDay, TimeClockEntriesBatchResult
from .create_time_clock_entry import CreateTimeClockEntryUseCase

# Tope de días por lote (RF-A3) — constante de producto, no de `Settings`:
# mismo criterio que `_DEFAULT_WINDOW_DAYS` en `infrastructure/routes.py`,
# que tampoco vive en configuración.
MAX_BATCH_DAYS = 7


def _expand_absence_dates(
    ranges: list[tuple[date, date]], date_from: date, date_to: date
) -> set[date]:
    expanded: set[date] = set()
    for start, end in ranges:
        current = max(start, date_from)
        clipped_end = min(end, date_to)
        while current <= clipped_end:
            expanded.add(current)
            current += timedelta(days=1)
    return expanded


class CreateTimeClockEntriesBatchUseCase:
    def __init__(
        self,
        repository: ITimeClockRepository,
        create_unit_use_case: CreateTimeClockEntryUseCase,
        manual_entry_max_past_days: int,
    ):
        self._repository = repository
        self._create_unit_use_case = create_unit_use_case
        self._manual_entry_max_past_days = manual_entry_max_past_days

    async def execute(
        self,
        *,
        user_id: str,
        entity_id: str | None,
        date_from: date,
        date_to: date,
        clock_in_time: time,
        clock_out_time: time | None = None,
    ) -> TimeClockEntriesBatchResult:
        # Validación ESTRUCTURAL, previa a tocar el repositorio (EC5): un
        # rango invertido o demasiado largo no llega ni a clasificarse
        # día a día.
        if date_from > date_to:
            raise TimeClockBatchDateRangeInvertedError(
                "La fecha de inicio no puede ser posterior a la fecha de fin."
            )
        if (date_to - date_from).days + 1 > MAX_BATCH_DAYS:
            raise TimeClockBatchRangeTooLongError(
                f"El lote no puede abarcar más de {MAX_BATCH_DAYS} días."
            )

        holiday_dates = await self._repository.list_holiday_dates_for_entity(
            date_from, date_to, entity_id
        )
        holidays = set(holiday_dates)
        approved_ranges = await self._repository.list_approved_absence_ranges(
            user_id, date_from, date_to
        )
        absence_dates = _expand_absence_dates(approved_ranges, date_from, date_to)
        existing_entry_dates = await self._repository.list_existing_entry_dates(
            user_id, date_from, date_to
        )
        existing_dates = set(existing_entry_dates)

        today = today_in_madrid()
        oldest_allowed = today - timedelta(days=self._manual_entry_max_past_days)

        omissions: dict[date, TimeClockBatchOmissionReason] = {}
        candidates: list[date] = []

        current = date_from
        while current <= date_to:
            if current.weekday() >= 5:  # 5=sábado, 6=domingo
                omissions[current] = TimeClockBatchOmissionReason.FIN_DE_SEMANA
            elif current in holidays:
                omissions[current] = TimeClockBatchOmissionReason.FESTIVO
            elif current in absence_dates:
                omissions[current] = TimeClockBatchOmissionReason.AUSENCIA
            elif current in existing_dates:
                omissions[current] = TimeClockBatchOmissionReason.YA_REGISTRADO
            elif current < oldest_allowed:
                omissions[current] = TimeClockBatchOmissionReason.FUERA_DE_VENTANA
            elif current > today:
                # LOGIC-2: día laborable futuro SIN ninguna exclusión de
                # calendario que lo cubra — rechaza TODO el lote antes de
                # escribir nada en BD (ni siquiera los días pasados válidos
                # ya clasificados en esta misma pasada).
                raise TimeClockBatchFutureDateError(
                    "El lote incluye un día futuro sin ninguna exclusión de "
                    "calendario que lo cubra — no se puede fichar por "
                    "adelantado."
                )
            else:
                candidates.append(current)
            current += timedelta(days=1)

        # RACE-1 (auditoría QA, severidad ALTA): el bucle de escritura NO
        # tenía transacción envolvente — cada día llamaba a
        # `CreateTimeClockEntryUseCase.execute()` con su propia conexión en
        # autocommit. Si un día a mitad de lote fallaba (p. ej.
        # `TimeClockOverlapError` por el constraint EXCLUDE bajo
        # concurrencia real: doble clic en "Guardar", o dos pestañas
        # enviando lotes solapados), la excepción subía y el cliente recibía
        # el error "como si nada se hubiera creado", pero los días previos
        # ya habían quedado persistidos. `repository.transaction()` agrupa
        # TODAS las escrituras del lote en una única transacción: un fallo
        # a mitad revierte también los días ya creados en esta pasada. Se
        # omite abrir la transacción si no hay candidatos (lote 100% omitido
        # por calendario) para no pedir una conexión del pool sin necesidad.
        created = []
        if candidates:
            async with self._repository.transaction():
                for work_date in candidates:
                    entry = await self._create_unit_use_case.execute(
                        user_id=user_id,
                        work_date=work_date,
                        clock_in=datetime.combine(
                            work_date, clock_in_time, tzinfo=MADRID_TZ
                        ),
                        clock_out=(
                            datetime.combine(
                                work_date, clock_out_time, tzinfo=MADRID_TZ
                            )
                            if clock_out_time is not None
                            else None
                        ),
                    )
                    created.append(entry)

        omitted = [
            OmittedBatchDay(work_date=day, reason=reason.value)
            for day, reason in sorted(omissions.items())
        ]
        return TimeClockEntriesBatchResult(created=created, omitted=omitted)
