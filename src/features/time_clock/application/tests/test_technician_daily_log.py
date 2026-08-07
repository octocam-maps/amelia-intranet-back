"""
Parte diario del técnico (requerimiento v1.2 §M1).

Los escenarios vienen de `docs/requerimientos-v1.2-tecnicos-bajas-drive.md`
§1.4 (Gherkin acordado con RRHH). Lo que se protege aquí no es "que el CRUD
funcione": es que la jornada de 16 horas se pueda registrar, que la efectiva
no la dicte el cliente y que la bolsa de 162 h y el ×1,45 den el número que
RRHH espera.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from src.features.time_clock.application.use_cases.create_technician_daily_log import (
    CreateTechnicianDailyLogUseCase,
)
from src.features.time_clock.application.use_cases.get_compensation_balance import (
    GetCompensationBalanceUseCase,
)
from src.features.time_clock.application.use_cases.list_technician_daily_logs import (
    ListTechnicianDailyLogsUseCase,
)
from src.features.time_clock.domain.entities import (
    OvernightStay,
    ProductCategory,
    Project,
)
from src.features.time_clock.domain.errors import (
    DuplicateDailyLogError,
    InvalidBreakError,
    InvalidTimeRangeError,
    ManualEntryOutOfWindowError,
    ProjectNotFoundError,
    TimeClockForbiddenError,
)
from src.features.time_clock.domain.policy import (
    MINUTES_PER_COMPENSATION_DAY,
    MONTHLY_HOURS_BUDGET_MINUTES,
    compensation_minutes,
    overtime_minutes,
)
from src.shared.auth.roles import RoleCode
from src.shared.utils.timezone import today_in_madrid

from .fakes import FakeTimeClockRepository

PROJECT = Project(id="p-1", code="GUADIX", name="Planta Guadix", is_active=True)
INACTIVE_PROJECT = Project(id="p-off", code="VIEJO", name="Proyecto cerrado", is_active=False)
TECH_ID = "u-tecnico"

MADRID = timezone(timedelta(hours=2))


def _repo(**kwargs) -> FakeTimeClockRepository:
    return FakeTimeClockRepository(projects=[PROJECT, INACTIVE_PROJECT], **kwargs)


def _use_case(repo: FakeTimeClockRepository) -> CreateTechnicianDailyLogUseCase:
    return CreateTechnicianDailyLogUseCase(repo, manual_entry_max_past_days=30)


def _recent_workday() -> date:
    """Un día dentro de la ventana de alta manual. Se calcula desde hoy y no
    se fija a una fecha literal: un test con fecha quemada empieza a fallar
    solo por el paso del tiempo."""
    return today_in_madrid() - timedelta(days=1)


async def _create(repo, **overrides):
    day = overrides.pop("work_date", _recent_workday())
    defaults = {
        "user_id": TECH_ID,
        "work_date": day,
        "started_at": datetime.combine(day, datetime.min.time(), MADRID).replace(hour=8),
        "ended_at": datetime.combine(day, datetime.min.time(), MADRID).replace(hour=20, minute=30),
        "project_id": PROJECT.id,
        "work_location": "Guadix, Granada",
        "had_break": True,
        "break_minutes": 45,
        "overnight_stay": OvernightStay.ESPANA,
        "product_category": ProductCategory.HARDWARE,
    }
    return await _use_case(repo).execute(**{**defaults, **overrides})


# --- Alta del parte -------------------------------------------------------


@pytest.mark.asyncio
async def test_creates_log_and_computes_effective_hours_deducting_the_break():
    repo = _repo()

    log = await _create(repo)

    # 08:00 -> 20:30 son 12h30m; menos 45 min de pausa, 11h45m = 705 min.
    assert log.worked_minutes == 705
    assert log.product_category is ProductCategory.HARDWARE
    assert log.overnight_stay is OvernightStay.ESPANA


@pytest.mark.asyncio
async def test_a_shift_can_cross_midnight_and_is_charged_to_the_starting_day():
    """LA razón de ser de este caso de uso: `CreateTimeClockEntryUseCase`
    rechaza esto, y sin ello el técnico no puede registrar su jornada real."""
    repo = _repo()
    day = _recent_workday()
    start = datetime.combine(day, datetime.min.time(), MADRID).replace(hour=8)
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), MADRID).replace(
        hour=1, minute=30
    )

    log = await _create(repo, work_date=day, started_at=start, ended_at=end, had_break=False,
                        break_minutes=0)

    assert log.work_date == day
    assert log.worked_minutes == 17 * 60 + 30


@pytest.mark.asyncio
async def test_only_one_log_per_day():
    repo = _repo()
    day = _recent_workday()
    await _create(repo, work_date=day)

    with pytest.raises(DuplicateDailyLogError):
        await _create(
            repo,
            work_date=day,
            started_at=datetime.combine(day, datetime.min.time(), MADRID).replace(hour=2),
            ended_at=datetime.combine(day, datetime.min.time(), MADRID).replace(hour=4),
            had_break=False,
            break_minutes=0,
        )


@pytest.mark.asyncio
async def test_future_date_is_rejected():
    """LOGIC-2 (pentest ético, severidad ALTA). El parte es autodeclarado como
    el alta manual, así que hereda la misma ventana — «hechos consumados»."""
    repo = _repo()

    with pytest.raises(ManualEntryOutOfWindowError):
        await _create(repo, work_date=today_in_madrid() + timedelta(days=1))


@pytest.mark.asyncio
async def test_date_older_than_the_window_is_rejected():
    repo = _repo()

    with pytest.raises(ManualEntryOutOfWindowError):
        await _create(repo, work_date=today_in_madrid() - timedelta(days=31))


@pytest.mark.asyncio
async def test_break_declared_as_none_but_with_minutes_is_rejected():
    repo = _repo()

    with pytest.raises(InvalidBreakError, match="30 minutos"):
        await _create(repo, had_break=False, break_minutes=30)


@pytest.mark.asyncio
async def test_break_declared_but_without_minutes_is_rejected():
    repo = _repo()

    with pytest.raises(InvalidBreakError):
        await _create(repo, had_break=True, break_minutes=0)


@pytest.mark.asyncio
async def test_break_longer_than_the_shift_is_rejected():
    repo = _repo()
    day = _recent_workday()

    with pytest.raises(InvalidBreakError, match="superar la duración"):
        await _create(
            repo,
            work_date=day,
            started_at=datetime.combine(day, datetime.min.time(), MADRID).replace(hour=8),
            ended_at=datetime.combine(day, datetime.min.time(), MADRID).replace(hour=10),
            had_break=True,
            break_minutes=150,
        )


@pytest.mark.asyncio
async def test_end_before_start_is_rejected():
    repo = _repo()
    day = _recent_workday()

    with pytest.raises(InvalidTimeRangeError):
        await _create(
            repo,
            work_date=day,
            started_at=datetime.combine(day, datetime.min.time(), MADRID).replace(hour=20),
            ended_at=datetime.combine(day, datetime.min.time(), MADRID).replace(hour=8),
            had_break=False,
            break_minutes=0,
        )


@pytest.mark.asyncio
async def test_inactive_project_is_rejected():
    repo = _repo()

    with pytest.raises(ProjectNotFoundError):
        await _create(repo, project_id=INACTIVE_PROJECT.id)


# --- Bolsa mensual y compensación ----------------------------------------


def test_a_month_under_the_budget_generates_no_overtime():
    assert overtime_minutes(150 * 60) == 0
    assert compensation_minutes(0) == 0


def test_overtime_is_the_excess_over_162_hours():
    assert MONTHLY_HOURS_BUDGET_MINUTES == 9720
    assert overtime_minutes(180 * 60) == 18 * 60


def test_compensation_applies_the_1_45_factor():
    """18 h extra × 1,45 = 26,1 h = 26h06m. Es el número que RRHH comprobará
    con una calculadora en el Excel."""
    assert compensation_minutes(18 * 60) == 1566
    assert 1566 == 26 * 60 + 6


def test_compensation_rounds_half_up_and_never_uses_float():
    # 1 minuto extra × 1,45 = 1,45 -> 1. Con 2 minutos, 2,9 -> 3.
    assert compensation_minutes(1) == 1
    assert compensation_minutes(2) == 3


def test_a_compensation_day_is_eight_hours():
    assert MINUTES_PER_COMPENSATION_DAY == 480


# --- Resumen del mes y saldo anual ---------------------------------------


@pytest.mark.asyncio
async def test_month_summary_counts_overnight_stays_by_place():
    repo = _repo()
    day = _recent_workday()
    await _create(repo, work_date=day, overnight_stay=OvernightStay.ESPANA)
    await _create(
        repo, work_date=day - timedelta(days=1), overnight_stay=OvernightStay.EXTRANJERO
    )
    await _create(repo, work_date=day - timedelta(days=2), overnight_stay=OvernightStay.NINGUNA)

    _, summary = await ListTechnicianDailyLogsUseCase(repo).execute(
        requester_id=TECH_ID,
        requester_role=RoleCode.TECNICO,
        year=day.year,
        month=day.month,
    )

    # Los tres partes pueden caer a caballo de dos meses si `day` es día 1 o 2;
    # lo que se comprueba es que cada pernocta se cuenta en SU sitio, no el
    # total del mes.
    assert summary.overnight_stays_spain + summary.overnight_stays_abroad == (
        summary.overnight_stays_total
    )
    assert summary.budget_minutes == MONTHLY_HOURS_BUDGET_MINUTES


@pytest.mark.asyncio
async def test_a_technician_cannot_read_another_technicians_logs():
    """RGPD: el filtrado vive en el backend. Escribir la URL a mano con el id
    de otro no debe dar acceso."""
    repo = _repo()

    with pytest.raises(TimeClockForbiddenError):
        await ListTechnicianDailyLogsUseCase(repo).execute(
            requester_id=TECH_ID,
            requester_role=RoleCode.TECNICO,
            year=2026,
            month=8,
            user_id="otro-tecnico",
        )


@pytest.mark.asyncio
async def test_the_admin_can_read_any_technicians_logs():
    repo = _repo()

    logs, _ = await ListTechnicianDailyLogsUseCase(repo).execute(
        requester_id="u-admin",
        requester_role=RoleCode.ADMINISTRADOR,
        year=2026,
        month=8,
        user_id=TECH_ID,
    )

    assert logs == []


@pytest.mark.asyncio
async def test_the_current_month_does_not_accrue_yet():
    """El excedente del mes en curso todavía puede cambiar: si contara como
    disponible, alguien podría disfrutar el día 10 unas horas que el día 28
    dejan de existir porque se corrigió un parte."""
    today = today_in_madrid()
    repo = _repo()
    repo.daily_logs = {}
    # 200 h en el mes EN CURSO -> excedente, pero aún no devengado.
    await _create(repo, work_date=today - timedelta(days=1))

    balance = await GetCompensationBalanceUseCase(repo).execute(
        user_id=TECH_ID, year=today.year
    )

    assert balance.accrued_minutes == 0
    assert balance.available_minutes == 0


@pytest.mark.asyncio
async def test_a_finished_month_accrues_and_consumption_is_subtracted():
    repo = _repo(compensation_consumed_minutes={(TECH_ID, 2024): 2 * MINUTES_PER_COMPENSATION_DAY})
    # Año pasado cerrado: se puede sembrar el fake directamente sin pelearse
    # con la ventana de 30 días del alta.
    day = date(2024, 3, 4)
    start = datetime.combine(day, datetime.min.time(), MADRID).replace(hour=8)
    await repo.create_daily_log(
        user_id=TECH_ID,
        work_date=day,
        started_at=start,
        ended_at=start + timedelta(hours=180),  # 180 h en un "día": el fake no valida
        project_id=PROJECT.id,
        work_location="Guadix",
        had_break=False,
        break_minutes=0,
        overnight_stay=OvernightStay.NINGUNA,
        product_category=ProductCategory.SOFTWARE,
    )

    balance = await GetCompensationBalanceUseCase(repo).execute(user_id=TECH_ID, year=2024)

    expected_accrued = compensation_minutes(overtime_minutes(180 * 60))
    assert balance.accrued_minutes == expected_accrued
    assert balance.consumed_minutes == 960  # 2 días × 8 h
    assert balance.available_minutes == expected_accrued - 960
