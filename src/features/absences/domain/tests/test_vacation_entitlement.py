"""Tests de la función PURA de cálculo del entitlement de vacaciones.

Cubren la política de la «Política Laboral Amelia Hub 2026» §5-§6 (23 días base
+ tramos por antigüedad), que DEROGA el cálculo por semestres de 20 días — ver
el docstring de `vacation_entitlement.py`."""

from datetime import date

from src.features.absences.domain.vacation_entitlement import (
    calculate_vacation_entitlement_days,
    resolve_vacation_entitlement_days,
)

# ── Base: 23 días por año completo ───────────────────────────────────────────


def test_full_year_worked_grants_the_base_of_twenty_three_days():
    """Contratado en un año anterior, sin llegar al tramo de 3 años -> 23."""
    assert calculate_vacation_entitlement_days(date(2025, 3, 10), 2026) == 23.0


def test_first_and_second_year_stay_on_the_base():
    """La matriz de §6 da 23 días tanto a "12 meses" como a "1-2 años": el
    primer tramo que sube es el de 3 años."""
    assert calculate_vacation_entitlement_days(date(2024, 3, 1), 2026) == 23.0
    assert calculate_vacation_entitlement_days(date(2025, 3, 1), 2026) == 23.0


# ── Tramos por antigüedad (§6) ───────────────────────────────────────────────


def test_three_years_of_seniority_grants_twenty_four_days():
    """Alta en marzo de 2023: cumple 3 años en marzo de 2026 y quedan 9 meses
    de año natural, así que el tramo aplica YA en 2026."""
    assert calculate_vacation_entitlement_days(date(2023, 3, 15), 2026) == 24.0


def test_five_years_of_seniority_grants_twenty_five_days():
    assert calculate_vacation_entitlement_days(date(2021, 2, 1), 2026) == 25.0


def test_four_years_still_on_the_twenty_four_tier():
    """El tramo "3-4 años" cubre los dos años: 24 días, no 25."""
    assert calculate_vacation_entitlement_days(date(2022, 1, 1), 2026) == 24.0


# ── Regla de los seis meses (§6) ─────────────────────────────────────────────


def test_anniversary_in_the_second_half_delays_the_tier_to_next_year():
    """Alta en septiembre de 2023: cumple 3 años en septiembre de 2026, con solo
    3 meses de año natural por delante. La política lo retrasa -> 23 en 2026."""
    assert calculate_vacation_entitlement_days(date(2023, 9, 15), 2026) == 23.0


def test_the_delayed_tier_applies_the_following_year():
    """El mismo caso, un año después: en 2027 ya cobra los 24 días."""
    assert calculate_vacation_entitlement_days(date(2023, 9, 15), 2027) == 24.0


def test_june_anniversary_falls_on_the_next_year_side():
    """Borde de la regla: con el aniversario en junio quedan 6 meses, y el
    documento dice "seis o menos" -> año siguiente. Es la interpretación fijada
    en `_seniority_years_effective_for`, pendiente de confirmar con RRHH."""
    assert calculate_vacation_entitlement_days(date(2023, 6, 1), 2026) == 23.0
    assert calculate_vacation_entitlement_days(date(2023, 5, 1), 2026) == 24.0


# ── Año de incorporación: prorrateo ──────────────────────────────────────────


def test_incorporation_on_january_first_grants_the_full_base():
    """Alta el 1 de enero: los 12 meses del año son trabajados -> 23 días
    completos, sin prorrateo que aplicar."""
    assert calculate_vacation_entitlement_days(date(2026, 1, 1), 2026) == 23.0


def test_incorporation_in_july_grants_half_the_base():
    """Julio..diciembre = 6 de 12 meses -> 11,5 días, que es medio día exacto y
    no necesita redondeo."""
    assert calculate_vacation_entitlement_days(date(2026, 7, 1), 2026) == 11.5


def test_incorporation_in_december_still_grants_something():
    """Un solo mes trabajado -> 23/12 = 1,92 -> 2,0 al medio día hacia arriba.

    Con el cálculo por semestres anterior esto daba 0 días, que es lo que
    obligaba al admin a poner un override a mano para cualquier alta de última
    hora del año."""
    assert calculate_vacation_entitlement_days(date(2026, 12, 1), 2026) == 2.0


def test_incorporation_in_september_is_prorated_not_zeroed():
    """Septiembre..diciembre = 4 de 12 meses -> 7,67 -> 8,0. El cálculo antiguo
    daba 0 por no llegar a un semestre completo."""
    assert calculate_vacation_entitlement_days(date(2026, 9, 1), 2026) == 8.0


def test_prorated_days_always_land_on_a_half_day():
    """Ningún mes de alta puede producir un saldo que no se pueda gastar: todos
    los resultados son múltiplos de 0,5."""
    for month in range(1, 13):
        days = calculate_vacation_entitlement_days(date(2026, month, 1), 2026)
        assert (days * 2) % 1 == 0, f"mes {month} dio {days}"


# ── Bordes y fallbacks ───────────────────────────────────────────────────────


def test_hire_date_none_falls_back_to_zero():
    """Sin `hire_date` (usuario legado) no hay base para calcular -> 0,
    documentado como fallback explícito, no un valor inventado."""
    assert calculate_vacation_entitlement_days(None, 2026) == 0.0


def test_hire_date_in_the_future_grants_zero_days():
    """El contrato todavía no había empezado ese año de referencia -> 0."""
    assert calculate_vacation_entitlement_days(date(2027, 1, 1), 2026) == 0.0


# ── `resolve_*`: el override manda ───────────────────────────────────────────


def test_resolve_uses_override_when_set_even_if_calculation_would_differ():
    """El override manual del admin MANDA sobre el cálculo automático,
    aunque `hire_date` diera un resultado distinto."""
    assert (
        resolve_vacation_entitlement_days(
            hire_date=date(2026, 9, 1),  # calcularía 8,0
            vacation_days_override=15.0,
            year=2026,
        )
        == 15.0
    )


def test_resolve_falls_back_to_calculation_when_no_override():
    assert (
        resolve_vacation_entitlement_days(
            hire_date=date(2020, 1, 1),
            vacation_days_override=None,
            year=2026,
        )
        == 25.0
    )


def test_resolve_override_zero_is_respected_not_treated_as_unset():
    """`0` es un override válido (distinto de `None`) — no debe caer al
    cálculo automático."""
    assert (
        resolve_vacation_entitlement_days(
            hire_date=date(2020, 1, 1),  # calcularía 25
            vacation_days_override=0.0,
            year=2026,
        )
        == 0.0
    )
