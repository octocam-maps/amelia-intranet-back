"""Tests de la función PURA de cálculo del entitlement de vacaciones
(decisión de negocio que deroga el "23 días/año" fijo de RF §4.1.2 — ver
docstring de `vacation_entitlement.py`)."""

from datetime import date

from src.features.absences.domain.vacation_entitlement import (
    calculate_vacation_entitlement_days,
    resolve_vacation_entitlement_days,
)


def test_full_year_worked_grants_twenty_days():
    """Contratado en un año anterior al de referencia -> 2 semestres -> 20."""
    assert calculate_vacation_entitlement_days(date(2020, 3, 10), 2026) == 20.0


def test_incorporation_year_with_six_to_eleven_months_grants_ten_days():
    """Alta el 1 de julio: julio..diciembre = 6 meses completos -> 1
    semestre -> 10 días (límite inferior del tramo 6-11 meses)."""
    assert calculate_vacation_entitlement_days(date(2026, 7, 1), 2026) == 10.0


def test_incorporation_year_with_eleven_months_still_grants_ten_days():
    """11 meses trabajados (alta en febrero) siguen siendo 1 semestre
    completo -> 10 días (el segundo semestre no se completa hasta el mes 12)."""
    assert calculate_vacation_entitlement_days(date(2026, 2, 1), 2026) == 10.0


def test_incorporation_year_with_less_than_six_months_grants_zero_days():
    """Alta el 1 de septiembre: septiembre..diciembre = 4 meses -> 0
    semestres completos -> 0 días (el admin puede fijar un override)."""
    assert calculate_vacation_entitlement_days(date(2026, 9, 1), 2026) == 0.0


def test_hire_date_none_falls_back_to_zero():
    """Sin `hire_date` (usuario legado) no hay base para calcular -> 0,
    documentado como fallback explícito, no un valor inventado."""
    assert calculate_vacation_entitlement_days(None, 2026) == 0.0


def test_hire_date_in_the_future_grants_zero_days():
    """El contrato todavía no había empezado ese año de referencia -> 0."""
    assert calculate_vacation_entitlement_days(date(2027, 1, 1), 2026) == 0.0


def test_incorporation_on_january_first_counts_as_full_year():
    """Alta el 1 de enero: los 12 meses del año son trabajados -> 20 días,
    igual que un año completo de un empleado ya veterano."""
    assert calculate_vacation_entitlement_days(date(2026, 1, 1), 2026) == 20.0


def test_resolve_uses_override_when_set_even_if_calculation_would_differ():
    """El override manual del admin MANDA sobre el cálculo automático,
    aunque `hire_date` diera un resultado distinto."""
    assert (
        resolve_vacation_entitlement_days(
            hire_date=date(2026, 9, 1),  # calcularía 0
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
        == 20.0
    )


def test_resolve_override_zero_is_respected_not_treated_as_unset():
    """`0` es un override válido (distinto de `None`) — no debe caer al
    cálculo automático."""
    assert (
        resolve_vacation_entitlement_days(
            hire_date=date(2020, 1, 1),  # calcularía 20
            vacation_days_override=0.0,
            year=2026,
        )
        == 0.0
    )
