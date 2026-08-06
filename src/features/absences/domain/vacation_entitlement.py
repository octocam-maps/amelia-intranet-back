"""
Cálculo automático del entitlement anual de vacaciones a partir de la fecha
de contratación (`users.hire_date`).

POLÍTICA VIGENTE — «Política Laboral Amelia Hub 2026», §5 y §6, entregada por
RRHH el 2026-08-06 y publicada como manual de lectura obligatoria del paso 3
(`/manuales/politica-laboral-amelia-2026.pdf`, migración 046).

    Base común: 23 días laborables anuales.

    Antigüedad      Vacaciones
    12 meses        23 días
    1 - 2 años      23 días
    3 - 4 años      24 días
    + 5 años        25 días

ESTO DEROGA EL CÁLCULO ANTERIOR de 10 días por semestre completo, que daba 20
días por año trabajado. Aquel derogaba a su vez el "23 días/año" fijo de
RF §4.1.2, así que la política vuelve a la cifra del requerimiento y le añade los
tramos por antigüedad, que hasta ahora no existían en el sistema.

Decisión del team-lead (2026-08-06): manda el DOCUMENTO. El manual es lo que la
plantilla lee y acepta en su onboarding, así que el contador de la intranet tiene
que cuadrar con él y no al revés — quien lee 23 y ve 20 en su saldo tiene razón.

DOS INTERPRETACIONES QUE EL DOCUMENTO NO CIERRA Y AQUÍ SE FIJAN (pendientes de
confirmar con RRHH):

1. PRORRATEO DEL AÑO DE INCORPORACIÓN. El documento dice "23 días laborables de
   vacaciones ANUALES" y no dice qué pasa en un año trabajado a medias. Se
   prorratea por meses trabajados, porque el devengo proporcional al tiempo de
   servicio es lo que fija el art. 38 ET: sin prorrateo, quien entra el 1 de
   diciembre tendría 23 días por un mes de trabajo. El redondeo va al MEDIO DÍA
   hacia arriba, a favor del trabajador.

2. EL BORDE DE LA "REGLA DE LOS SEIS MESES". El documento aplica el nuevo tramo
   en el mismo año si al alcanzarlo "restan más de seis (6) meses para la
   finalización del año natural", y desde el año siguiente si restan "seis o
   menos". Se resuelve a nivel de MES del aniversario (ver
   `_seniority_years_effective_for`): aniversario de enero a mayo -> mismo año;
   de junio en adelante -> el siguiente.

"Meses completos trabajados dentro del año" se cuenta de forma calendario
(no por día exacto): el propio mes de alta cuenta como mes trabajado, igual
que todos los meses hasta diciembre inclusive. No hay política de baja/cese
(no existe columna de fin de contrato todavía), así que esta función asume
que el contrato sigue vigente en todo el resto del año de referencia.

Función PURA — sin dependencias de framework/SQL (GOLDEN RULE: domain no
importa infrastructure). Vive en `absences` (el feature dueño del concepto
"entitlement"/`AbsenceBalance`) aunque la consume también `staff.infrastructure`
(que ya cruza a las tablas de `absences` desde antes, ver
`staff/infrastructure/repositories/staff_repository.py`).
"""

import math
from datetime import date

BASE_DAYS = 23.0

# Tramos de antigüedad de §6, del más alto al más bajo: (años cumplidos, días).
# Se recorre en orden y gana el primero que se alcanza, así que añadir un tramo
# es insertar una tupla — sin tocar la lógica.
SENIORITY_TIERS: tuple[tuple[int, float], ...] = (
    (5, 25.0),
    (3, 24.0),
)

MONTHS_PER_YEAR = 12

# Umbral de la "regla de los seis meses" (§6). Si desde el mes del aniversario
# quedan MÁS de estos meses hasta fin de año, el nuevo tramo aplica ya ese año.
MONTHS_REMAINING_FOR_SAME_YEAR = 6

# `hire_date is None`: no hay fecha de alta con la que calcular (p. ej. un
# usuario legado sembrado antes de 015_users_hire_date.sql). Fallback
# documentado a 0 días — el admin debe fijar un override manual mientras el
# dato no se complete, en vez de que el sistema invente una fecha.
FALLBACK_DAYS_WHEN_HIRE_DATE_UNKNOWN = 0.0


def _round_to_half_day(days: float) -> float:
    """Redondea al medio día HACIA ARRIBA.

    Hacia arriba a propósito: el prorrateo es una aproximación administrativa y
    el redondeo se resuelve a favor del trabajador. Al medio día porque es la
    unidad mínima con la que se piden ausencias en la plataforma — un saldo de
    1,92 días sería un número que nadie puede gastar."""
    return math.ceil(days * 2) / 2


def _seniority_years_effective_for(hire_date: date, year: int) -> int:
    """Años de antigüedad que CUENTAN para el entitlement de `year`.

    No es simplemente `year - hire_date.year`: la política retrasa al año
    siguiente el tramo cuyo aniversario cae con seis meses o menos por delante
    (§6). Así que un aniversario en la segunda mitad del año cuenta un año menos
    a estos efectos.

    Ejemplos con `year=2026`:
    - alta 2023-03-15 -> cumple 3 años en marzo, quedan 9 meses -> cuenta 3
      (24 días ya en 2026).
    - alta 2023-09-15 -> cumple 3 años en septiembre, quedan 3 meses -> cuenta 2
      (23 días en 2026, y 24 a partir de 2027).
    """
    years_since_hire = year - hire_date.year
    months_remaining = MONTHS_PER_YEAR - hire_date.month
    if months_remaining > MONTHS_REMAINING_FOR_SAME_YEAR:
        return years_since_hire
    # El tramo que abre este aniversario todavía no aplica: cuenta como si aún no
    # se hubiera alcanzado. Nunca por debajo de 0.
    return max(years_since_hire - 1, 0)


def _days_for_seniority(seniority_years: int) -> float:
    """Días que corresponden a esa antigüedad según la matriz de §6."""
    for tier_years, tier_days in SENIORITY_TIERS:
        if seniority_years >= tier_years:
            return tier_days
    return BASE_DAYS


def calculate_vacation_entitlement_days(hire_date: date | None, year: int) -> float:
    """Días de vacaciones que corresponden a `year` dado `hire_date`.

    Casos:
    - `hire_date is None` -> `FALLBACK_DAYS_WHEN_HIRE_DATE_UNKNOWN` (0).
    - `hire_date.year > year` -> el contrato todavía no había empezado ese
      año -> 0.
    - `hire_date.year < year` -> año completo trabajado -> los días de su tramo
      de antigüedad (23, 24 o 25).
    - `hire_date.year == year` -> año de incorporación -> prorrateo de la base
      por los meses trabajados, contando el propio mes de alta.
    """
    if hire_date is None:
        return FALLBACK_DAYS_WHEN_HIRE_DATE_UNKNOWN

    if hire_date.year > year:
        return 0.0

    if hire_date.year < year:
        return _days_for_seniority(_seniority_years_effective_for(hire_date, year))

    # Año de incorporación: se prorratea la BASE — nadie tiene antigüedad de tramo
    # el año en que entra.
    months_worked = MONTHS_PER_YEAR - hire_date.month + 1
    return _round_to_half_day(BASE_DAYS * months_worked / MONTHS_PER_YEAR)


def resolve_vacation_entitlement_days(
    *, hire_date: date | None, vacation_days_override: float | None, year: int
) -> float:
    """Fuente única para resolver el entitlement efectivo de un año: el
    override manual del admin manda si está fijado (no NULL); si no hay
    override, se calcula automáticamente desde `hire_date`."""
    if vacation_days_override is not None:
        return float(vacation_days_override)
    return calculate_vacation_entitlement_days(hire_date, year)
