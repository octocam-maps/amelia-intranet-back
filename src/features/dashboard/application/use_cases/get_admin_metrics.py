"""
Caso de uso: métricas del Home del administrador
(`GET /dashboard/admin/metrics`) — KPIs, sparklines del periodo y radar de
asistencia (top 5 desvíos). Solo lectura, agrega `time_clock_entries` y
`absence_requests` (ver nota de diseño en `domain/entities.py`).

Reglas de negocio documentadas aquí (no en el repositorio SQL):

- **Jornada estándar**: 8h/día (`_STANDARD_WORKDAY_MINUTES`) — asunción
  explícita del enunciado, no viene de una tabla de configuración todavía.
- **Puntualidad**: puntual si la entrada es <= 09:00 hora de Madrid. El KPI
  del periodo se deriva de la MISMA serie diaria que las sparklines (suma de
  puntuales/total), para no duplicar la consulta ni arriesgar que ambos
  números diverjan.
- **Radar de asistencia**: por empleado se calcula la magnitud de 3 posibles
  desvíos (entrada tardía, salida con horas extra, déficit de horas
  acumulado) y se clasifica con el de mayor magnitud (`_classify`). Si los
  tres están por debajo de `_DEVIATION_THRESHOLD_MINUTES`, se clasifica como
  "on_time" con magnitud 0. La selección de los 5 finales
  (`_build_attendance_radar`) prioriza tener al menos un representante de
  cada tipo de desvío disponible (variedad para la demo, pedido explícito
  del enunciado) y rellena el resto por magnitud; el ORDEN final siempre es
  descendente por `value_minutes`.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from src.shared.utils.timezone import today_in_madrid

from ...domain.entities import (
    AdminDashboardMetrics,
    AdminMetricsKPIs,
    AttendanceRadarItem,
    DailyTrendPoint,
    EmployeeAttendanceStats,
    MetricsTrends,
)
from ...domain.ports import IDashboardRepository

_STANDARD_WORKDAY_MINUTES = 8 * 60
_WORKDAY_START_MINUTES = 9 * 60  # 09:00
_WORKDAY_END_MINUTES = 19 * 60  # 19:00
# Umbral por debajo del cual una desviación no cuenta como tal — criterio de
# producto para la demo (documentado, no viene del requerimiento funcional).
_DEVIATION_THRESHOLD_MINUTES = 15
_RADAR_SIZE = 5
_DEVIATION_KINDS = ("late_in", "overtime_out", "negative_balance")


class GetAdminMetricsUseCase:
    def __init__(self, repository: IDashboardRepository):
        self._repository = repository

    async def execute(
        self,
        *,
        entity_id: Optional[str] = None,
        department_id: Optional[str] = None,
        period_days: int = 14,
    ) -> AdminDashboardMetrics:
        # TZ-1 (ver src/shared/utils/timezone.py): "hoy" es Europe/Madrid.
        today = today_in_madrid()
        from_date = today - timedelta(days=period_days - 1)

        absent_today = await self._repository.count_absent_today(
            today, entity_id, department_id
        )
        pending_approvals = await self._repository.count_pending_absence_approvals(
            entity_id, department_id
        )
        clocked_in_now = await self._repository.count_clocked_in_now_filtered(
            today, entity_id, department_id
        )
        daily_points = await self._repository.list_daily_trends(
            from_date, today, entity_id, department_id
        )
        attendance_stats = await self._repository.list_attendance_stats(
            from_date, today, entity_id, department_id
        )

        kpis = AdminMetricsKPIs(
            absent_today=absent_today,
            pending_approvals=pending_approvals,
            clocked_in_now=clocked_in_now,
            punctuality_pct=_period_punctuality_pct(daily_points),
        )
        trends = _build_trends(daily_points)
        attendance_radar = _build_attendance_radar(attendance_stats)

        return AdminDashboardMetrics(kpis=kpis, trends=trends, attendance_radar=attendance_radar)


def _build_trends(points: list[DailyTrendPoint]) -> MetricsTrends:
    return MetricsTrends(
        absences=[p.absences for p in points],
        clocked_in=[p.clocked_in for p in points],
        punctuality=[_pct(p.punctual_entries, p.total_entries) for p in points],
    )


def _period_punctuality_pct(points: list[DailyTrendPoint]) -> int:
    total = sum(p.total_entries for p in points)
    punctual = sum(p.punctual_entries for p in points)
    return _pct(punctual, total)


def _pct(numerator: int, denominator: int) -> int:
    if denominator == 0:
        return 0
    return round(numerator / denominator * 100)


def _format_time(minutes_since_midnight: float) -> str:
    total_minutes = int(round(minutes_since_midnight)) % (24 * 60)
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def _format_deficit(deficit_minutes: int) -> str:
    hours, minutes = divmod(deficit_minutes, 60)
    if minutes:
        return f"-{hours}h {minutes}m acumulado"
    return f"-{hours}h acumulado"


@dataclass(frozen=True)
class _Candidate:
    item: AttendanceRadarItem
    magnitude: int


def _classify(stat: EmployeeAttendanceStats) -> _Candidate:
    late_in_minutes = max(0, round(stat.avg_clock_in_minutes - _WORKDAY_START_MINUTES))
    overtime_minutes = max(0, round(stat.avg_clock_out_minutes - _WORKDAY_END_MINUTES))
    expected_minutes = stat.days_clocked * _STANDARD_WORKDAY_MINUTES
    deficit_minutes = max(0, round(expected_minutes - stat.worked_minutes_total))

    magnitudes = {
        "late_in": late_in_minutes,
        "overtime_out": overtime_minutes,
        "negative_balance": deficit_minutes,
    }
    dominant_kind = max(magnitudes, key=lambda k: magnitudes[k])
    dominant_magnitude = magnitudes[dominant_kind]

    if dominant_magnitude < _DEVIATION_THRESHOLD_MINUTES:
        detail = f"Entrada {_format_time(stat.avg_clock_in_minutes)} · sin desvíos"
        item = AttendanceRadarItem(
            user_id=stat.user_id,
            full_name=stat.full_name,
            avatar_url=stat.avatar_url,
            kind="on_time",
            value_minutes=0,
            detail=detail,
        )
        return _Candidate(item=item, magnitude=0)

    if dominant_kind == "late_in":
        detail = f"Entrada {_format_time(stat.avg_clock_in_minutes)} (media)"
    elif dominant_kind == "overtime_out":
        detail = f"Salida {_format_time(stat.avg_clock_out_minutes)}"
    else:
        detail = _format_deficit(deficit_minutes)

    item = AttendanceRadarItem(
        user_id=stat.user_id,
        full_name=stat.full_name,
        avatar_url=stat.avatar_url,
        kind=dominant_kind,
        value_minutes=dominant_magnitude,
        detail=detail,
    )
    return _Candidate(item=item, magnitude=dominant_magnitude)


def _build_attendance_radar(stats: list[EmployeeAttendanceStats]) -> list[AttendanceRadarItem]:
    candidates = [_classify(s) for s in stats]

    buckets: dict[str, list[_Candidate]] = {}
    for candidate in candidates:
        buckets.setdefault(candidate.item.kind, []).append(candidate)
    for bucket in buckets.values():
        bucket.sort(key=lambda c: c.magnitude, reverse=True)

    selected: list[_Candidate] = []
    selected_ids: set[str] = set()

    # 1) Un representante del desvío más notable de cada tipo disponible,
    #    para garantizar variedad — nunca gastamos un slot en "on_time" en
    #    esta primera pasada.
    for kind in _DEVIATION_KINDS:
        if len(selected) >= _RADAR_SIZE:
            break
        bucket = buckets.get(kind, [])
        if bucket:
            top = bucket[0]
            selected.append(top)
            selected_ids.add(top.item.user_id)

    # 2) Rellenar los slots que queden con la mayor magnitud disponible,
    #    de cualquier tipo (incluido "on_time" si no queda nada más).
    remaining = sorted(
        (c for c in candidates if c.item.user_id not in selected_ids),
        key=lambda c: c.magnitude,
        reverse=True,
    )
    for candidate in remaining:
        if len(selected) >= _RADAR_SIZE:
            break
        selected.append(candidate)
        selected_ids.add(candidate.item.user_id)

    selected.sort(key=lambda c: c.magnitude, reverse=True)
    return [c.item for c in selected[:_RADAR_SIZE]]
