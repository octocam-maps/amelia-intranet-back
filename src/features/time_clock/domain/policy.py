"""
Reglas numéricas del régimen de bolsa de horas del técnico (requerimiento
v1.2 §M1). Único sitio donde viven estos techos — mismo criterio que
`onboarding/domain/policy.py::MAX_QUIZ_ATTEMPTS`: si el número aparece en dos
sitios, tarde o temprano solo se cambia uno.

Todo se calcula en MINUTOS enteros y el factor en `Decimal`. Nada de `float`:
estos minutos acaban convertidos en días de descanso que alguien disfruta, y
un 0.1 que no se puede representar en binario no es un detalle académico
cuando el resultado es "te quedan 1,9999 días".
"""

from decimal import ROUND_HALF_UP, Decimal

# Bolsa mensual del técnico: 162 h del día 1 al último del mes.
MONTHLY_HOURS_BUDGET_MINUTES = 162 * 60  # 9720

# Cada hora que supera la bolsa se compensa con 1,45 h de descanso.
OVERTIME_COMPENSATION_FACTOR = Decimal("1.45")

# Cuántos minutos "gasta" un día de descanso compensatorio. RRHH pide restar
# DÍAS de un saldo que se devenga en HORAS, así que hace falta este divisor;
# el saldo se guarda y se calcula siempre en minutos, y los días son solo
# presentación.
MINUTES_PER_COMPENSATION_DAY = 8 * 60  # 480


def overtime_minutes(worked_minutes: int) -> int:
    """Excedente del mes sobre la bolsa. Nunca negativo: un mes por debajo de
    las 162 h no genera déficit ni se arrastra al siguiente (supuesto adoptado
    en `docs/requerimientos-v1.2-tecnicos-bajas-drive.md` §1.10, pendiente de
    confirmación por RRHH)."""
    return max(0, worked_minutes - MONTHLY_HOURS_BUDGET_MINUTES)


def compensation_minutes(overtime: int) -> int:
    """Descanso que devengan esas horas extra, redondeado al minuto.

    `ROUND_HALF_UP` y no el banquero por defecto de `Decimal`: es tiempo de
    descanso de una persona y el redondeo debe ser el que cualquiera espera al
    comprobarlo con una calculadora.
    """
    return int(
        (Decimal(overtime) * OVERTIME_COMPENSATION_FACTOR).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
