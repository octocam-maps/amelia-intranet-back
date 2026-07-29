"""
Tests del alta de fichaje en lote (RF-A3) — orden de evaluación EC1-EC6.

LOGIC-2 (pentest ético, severidad ALTA): el fix cerrado por
`CreateTimeClockEntryUseCase._validate_window` es la garantía de seguridad
que este lote NO puede reabrir. El punto crítico de estos tests es EC2/EC6:
un día laborable futuro SIN ninguna exclusión de calendario que lo cubra
DEBE tumbar el lote entero, sin escribir ni un solo tramo — ni siquiera los
días pasados válidos del mismo lote.
"""

from datetime import UTC, date, datetime, time

import pytest

from src.features.time_clock.application.use_cases import (
    create_time_clock_entries_batch as batch_module,
)
from src.features.time_clock.application.use_cases import (
    create_time_clock_entry as unit_module,
)
from src.features.time_clock.application.use_cases.create_time_clock_entry import (
    CreateTimeClockEntryUseCase,
)
from src.features.time_clock.domain.errors import (
    TimeClockBatchDateRangeInvertedError,
    TimeClockBatchFutureDateError,
    TimeClockBatchRangeTooLongError,
    TimeClockOverlapError,
)

from .fakes import FakeTimeClockRepository

_ENTITY_HUB = "entity-hub"
_ENTITY_LAB = "entity-lab"
_USER_ID = "user-1"
_MAX_PAST_DAYS = 30


def _freeze_today(monkeypatch: pytest.MonkeyPatch, today: date) -> None:
    # Se congelan LOS DOS módulos: el use case del lote clasifica los días
    # contra "hoy", pero cada `Candidate` se delega en
    # `CreateTimeClockEntryUseCase`, que vuelve a comprobar "hoy" con su
    # propia referencia al helper — si solo se congelara uno de los dos, el
    # unitario usaría la fecha REAL del sistema y rompería el test.
    monkeypatch.setattr(batch_module, "today_in_madrid", lambda: today)
    monkeypatch.setattr(unit_module, "today_in_madrid", lambda: today)


def _build_use_case(
    repository: FakeTimeClockRepository,
    *,
    max_past_days: int = _MAX_PAST_DAYS,
) -> "batch_module.CreateTimeClockEntriesBatchUseCase":
    unit_use_case = CreateTimeClockEntryUseCase(
        repository, manual_entry_max_past_days=max_past_days
    )
    return batch_module.CreateTimeClockEntriesBatchUseCase(
        repository, unit_use_case, max_past_days
    )


def _d(day: int, month: int = 7, year: int = 2026) -> date:
    return date(year, month, day)


@pytest.mark.asyncio
async def test_ec1_weekend_days_are_omitted_and_the_rest_of_the_batch_is_accepted(
    monkeypatch,
):
    """Caso de uso principal: fichar la semana en curso un viernes,
    seleccionando lunes(13)->domingo(19). Sábado(18)/domingo(19) son
    futuros respecto a "hoy" (17), pero se omiten por `fin_de_semana`
    ANTES de llegar al chequeo de futuro — el lote se acepta."""
    today = _d(17)  # viernes
    _freeze_today(monkeypatch, today)
    repository = FakeTimeClockRepository()
    use_case = _build_use_case(repository)

    result = await use_case.execute(
        user_id=_USER_ID,
        entity_id=_ENTITY_HUB,
        date_from=_d(13),
        date_to=_d(19),
        clock_in_time=time(8, 0),
        clock_out_time=time(17, 0),
    )

    created_dates = {e.work_date for e in result.created}
    assert created_dates == {_d(13), _d(14), _d(15), _d(16), _d(17)}
    omitted_by_date = {o.work_date: o.reason for o in result.omitted}
    assert omitted_by_date == {_d(18): "fin_de_semana", _d(19): "fin_de_semana"}
    assert len(repository.entries) == 5


@pytest.mark.asyncio
async def test_ec2_future_workday_without_exclusion_rejects_the_whole_batch(
    monkeypatch,
):
    """Un día laborable futuro SIN festivo/ausencia que lo cubra DEBE
    rechazar el lote ENTERO (422), incluidos los días pasados válidos del
    mismo lote — cero tramos creados (LOGIC-2)."""
    today = _d(17)  # viernes
    _freeze_today(monkeypatch, today)
    repository = FakeTimeClockRepository()
    use_case = _build_use_case(repository)

    with pytest.raises(TimeClockBatchFutureDateError):
        await use_case.execute(
            user_id=_USER_ID,
            entity_id=_ENTITY_HUB,
            date_from=_d(16),  # jueves, pasado válido
            date_to=_d(22),  # miércoles siguiente, 7 días
            clock_in_time=time(8, 0),
            clock_out_time=time(17, 0),
        )

    assert len(repository.entries) == 0


@pytest.mark.asyncio
async def test_ec3_future_holiday_is_omitted_without_reaching_the_future_check(
    monkeypatch,
):
    """Festivo futuro dentro del rango: se omite por `festivo` sin llegar
    nunca al chequeo de "futuro" — si no hay OTRO día laborable futuro sin
    exclusión, el lote se acepta."""
    today = _d(17)  # viernes
    _freeze_today(monkeypatch, today)
    # día 20 (lunes): festivo futuro.
    repository = FakeTimeClockRepository(holidays=[(_d(20), _ENTITY_HUB)])
    use_case = _build_use_case(repository)

    result = await use_case.execute(
        user_id=_USER_ID,
        entity_id=_ENTITY_HUB,
        date_from=_d(16),
        date_to=_d(20),
        clock_in_time=time(8, 0),
        clock_out_time=time(17, 0),
    )

    omitted_by_date = {o.work_date: o.reason for o in result.omitted}
    assert omitted_by_date[_d(20)] == "festivo"
    created_dates = {e.work_date for e in result.created}
    assert _d(20) not in created_dates


@pytest.mark.asyncio
async def test_ec3_future_holiday_does_not_shield_another_unprotected_future_workday(
    monkeypatch,
):
    """El filtro de calendario NUNCA "salva" a un día laborable futuro sin
    exclusión propia: si el festivo cubre el 20 pero el 21 (martes futuro)
    no tiene ninguna exclusión, el 21 sigue tumbando el lote entero."""
    today = _d(17)  # viernes
    _freeze_today(monkeypatch, today)
    repository = FakeTimeClockRepository(holidays=[(_d(20), _ENTITY_HUB)])
    use_case = _build_use_case(repository)

    with pytest.raises(TimeClockBatchFutureDateError):
        await use_case.execute(
            user_id=_USER_ID,
            entity_id=_ENTITY_HUB,
            date_from=_d(16),
            date_to=_d(22),  # incluye el 21 (martes futuro, sin exclusión)
            clock_in_time=time(8, 0),
            clock_out_time=time(17, 0),
        )

    assert len(repository.entries) == 0


@pytest.mark.asyncio
async def test_ec4_approved_absence_covering_whole_range_is_accepted_fully_omitted(
    monkeypatch,
):
    """Ausencia aprobada futura que cubre TODO el rango: lote ACEPTADO con
    100% omitido por `ausencia`, 0 creados — no es un error."""
    today = _d(17)  # viernes
    _freeze_today(monkeypatch, today)
    repository = FakeTimeClockRepository(
        approved_absence_ranges={_USER_ID: [(_d(20), _d(24))]}  # lunes-viernes futuros
    )
    use_case = _build_use_case(repository)

    result = await use_case.execute(
        user_id=_USER_ID,
        entity_id=_ENTITY_HUB,
        date_from=_d(20),
        date_to=_d(24),
        clock_in_time=time(8, 0),
        clock_out_time=time(17, 0),
    )

    assert result.created == []
    assert len(result.omitted) == 5
    assert all(o.reason == "ausencia" for o in result.omitted)
    assert len(repository.entries) == 0


@pytest.mark.asyncio
async def test_ec5_range_longer_than_seven_days_is_rejected_before_classifying_any_day(
    monkeypatch,
):
    """Rango de 8 días: 422 estructural — ni siquiera se clasifica día a
    día (se valida ANTES de tocar el repositorio)."""
    today = _d(17)
    _freeze_today(monkeypatch, today)

    class _PoisonedRepository(FakeTimeClockRepository):
        async def list_holiday_dates_for_entity(self, *args, **kwargs):
            raise AssertionError("no debía clasificar ningún día: rango > 7 días")

        async def list_approved_absence_ranges(self, *args, **kwargs):
            raise AssertionError("no debía clasificar ningún día: rango > 7 días")

        async def list_existing_entry_dates(self, *args, **kwargs):
            raise AssertionError("no debía clasificar ningún día: rango > 7 días")

    repository = _PoisonedRepository()
    use_case = _build_use_case(repository)

    with pytest.raises(TimeClockBatchRangeTooLongError):
        await use_case.execute(
            user_id=_USER_ID,
            entity_id=_ENTITY_HUB,
            date_from=_d(13),
            date_to=_d(20),  # 8 días inclusive
            clock_in_time=time(8, 0),
            clock_out_time=time(17, 0),
        )


@pytest.mark.asyncio
async def test_ec6_out_of_window_mixed_with_future_workday_rejects_without_breakdown(
    monkeypatch,
):
    """Mezcla de `fuera_de_ventana` (2 días) + 1 día laborable futuro sin
    exclusión: el futuro aborta TODO antes de fijar ningún desglose — los
    2 días fuera de ventana nunca llegan a aparecer como "omitidos"."""
    today = _d(15)  # miércoles
    _freeze_today(monkeypatch, today)
    repository = FakeTimeClockRepository()
    use_case = _build_use_case(repository, max_past_days=0)  # hoy es el límite

    with pytest.raises(TimeClockBatchFutureDateError):
        await use_case.execute(
            user_id=_USER_ID,
            entity_id=_ENTITY_HUB,
            date_from=_d(13),  # lunes, fuera de ventana (max_past_days=0)
            date_to=_d(19),  # domingo, 7 días
            clock_in_time=time(8, 0),
            clock_out_time=time(17, 0),
        )

    assert len(repository.entries) == 0


@pytest.mark.asyncio
async def test_rejects_inverted_date_range(monkeypatch):
    """`date_from` posterior a `date_to`: 422 estructural, mismo nivel que
    el tope de 7 días."""
    _freeze_today(monkeypatch, _d(17))
    repository = FakeTimeClockRepository()
    use_case = _build_use_case(repository)

    with pytest.raises(TimeClockBatchDateRangeInvertedError):
        await use_case.execute(
            user_id=_USER_ID,
            entity_id=_ENTITY_HUB,
            date_from=_d(19),
            date_to=_d(13),
            clock_in_time=time(8, 0),
        )


@pytest.mark.asyncio
async def test_holiday_scoped_to_another_entity_does_not_omit_the_day(monkeypatch):
    """Festivo con `entity_id` distinto al del usuario: NO se omite, el día
    se procesa normalmente (tabla de casos de la spec)."""
    today = _d(17)  # viernes
    _freeze_today(monkeypatch, today)
    repository = FakeTimeClockRepository(holidays=[(_d(14), _ENTITY_LAB)])
    use_case = _build_use_case(repository)

    result = await use_case.execute(
        user_id=_USER_ID,
        entity_id=_ENTITY_HUB,
        date_from=_d(14),
        date_to=_d(14),
        clock_in_time=time(8, 0),
        clock_out_time=time(17, 0),
    )

    assert result.omitted == []
    assert len(result.created) == 1
    assert result.created[0].work_date == _d(14)


@pytest.mark.asyncio
async def test_batch_omits_a_day_that_already_has_an_entry(monkeypatch):
    today = _d(17)  # viernes
    _freeze_today(monkeypatch, today)
    repository = FakeTimeClockRepository()
    use_case = _build_use_case(repository)
    await repository.create_entry(
        user_id=_USER_ID,
        work_date=_d(14),
        clock_in=datetime(2026, 7, 14, 6, 0, tzinfo=UTC),
        clock_out=datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
        source="manual",
    )

    result = await use_case.execute(
        user_id=_USER_ID,
        entity_id=_ENTITY_HUB,
        date_from=_d(14),
        date_to=_d(14),
        clock_in_time=time(8, 0),
        clock_out_time=time(17, 0),
    )

    assert result.created == []
    assert len(result.omitted) == 1
    assert result.omitted[0].reason == "ya_registrado"


class _FailingOnNthCreateRepository(FakeTimeClockRepository):
    """Simula el `TimeClockOverlapError` que produce el constraint `EXCLUDE`
    de la migración 012 bajo concurrencia real (doble clic en "Guardar", o
    dos pestañas enviando lotes solapados) — el N-ésimo `create_entry` del
    bucle de escritura falla, los anteriores ya se habían ejecutado."""

    def __init__(self, *args, fail_on_call: int, **kwargs):
        super().__init__(*args, **kwargs)
        self._fail_on_call = fail_on_call
        self._create_calls = 0

    async def create_entry(self, **kwargs):
        self._create_calls += 1
        if self._create_calls == self._fail_on_call:
            raise TimeClockOverlapError("Fallo simulado del N-ésimo día del lote.")
        return await super().create_entry(**kwargs)


@pytest.mark.asyncio
async def test_race1_a_failure_mid_batch_write_leaves_zero_entries_persisted(
    monkeypatch,
):
    """RACE-1 (auditoría QA, severidad ALTA): el bucle de escritura del lote
    NO tenía transacción envolvente — cada día llamaba a
    `CreateTimeClockEntryUseCase.execute()` con su propia conexión en
    autocommit. Si el 3.º de 5 días fallaba, el cliente recibía un 422 "como
    si nada se hubiera creado", pero los 2 días anteriores ya habían quedado
    persistidos. El lote entero debe ser atómico: cero tramos si CUALQUIER
    día del bucle de escritura falla."""
    today = _d(17)  # viernes
    _freeze_today(monkeypatch, today)
    repository = _FailingOnNthCreateRepository(fail_on_call=3)
    use_case = _build_use_case(repository)

    with pytest.raises(TimeClockOverlapError):
        await use_case.execute(
            user_id=_USER_ID,
            entity_id=_ENTITY_HUB,
            date_from=_d(13),  # lunes
            date_to=_d(17),  # viernes, 5 días laborables candidatos
            clock_in_time=time(8, 0),
            clock_out_time=time(17, 0),
        )

    assert len(repository.entries) == 0


@pytest.mark.asyncio
async def test_created_entries_force_manual_source_with_madrid_wall_time(monkeypatch):
    """Delegar en `CreateTimeClockEntryUseCase` reutiliza al 100% el
    `source=manual` forzado — cero duplicación de esa regla en el lote."""
    today = _d(17)  # viernes
    _freeze_today(monkeypatch, today)
    repository = FakeTimeClockRepository()
    use_case = _build_use_case(repository)

    result = await use_case.execute(
        user_id=_USER_ID,
        entity_id=_ENTITY_HUB,
        date_from=_d(17),
        date_to=_d(17),
        clock_in_time=time(8, 30),
        clock_out_time=time(17, 15),
    )

    assert len(result.created) == 1
    entry = result.created[0]
    assert entry.source == "manual"
    assert entry.clock_in.hour == 8
    assert entry.clock_in.minute == 30
    assert entry.clock_out is not None
    assert entry.clock_out.hour == 17
    assert entry.clock_out.minute == 15
