"""
Cálculo automático del entitlement anual de vacaciones a partir de la fecha
de contratación (`users.hire_date`).

DECISIÓN DE NEGOCIO (posterior al requerimiento, DEROGA el "23 días/año" fijo
de RF §4.1.2): el devengo es de 10 días laborables por cada semestre
completo (6 meses) trabajado. Para el entitlement DEL AÑO EN CURSO (que es lo
que muestra el contador en plantilla/dashboard/saldo de ausencias):

    entitled_del_año = 10 * floor(meses_completos_trabajados_en_el_año / 6)

- Año trabajado completo (contratado en un año anterior al de referencia)
  -> floor(12/6) = 2 semestres -> 20 días.
- Año de incorporación con 6-11 meses trabajados ese año -> 1 semestre
  -> 10 días.
- Año de incorporación con menos de 6 meses trabajados -> 0 semestres
  -> 0 días (el admin puede subirlo a mano vía `users.vacation_days_override`,
  ver 027_users_vacation_days_override.sql).

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

from datetime import date
from typing import Optional

DAYS_PER_SEMESTER = 10
MONTHS_PER_SEMESTER = 6

# `hire_date is None`: no hay fecha de alta con la que calcular (p. ej. un
# usuario legado sembrado antes de 015_users_hire_date.sql). Fallback
# documentado a 0 días — el admin debe fijar un override manual mientras el
# dato no se complete, en vez de que el sistema invente una fecha.
FALLBACK_DAYS_WHEN_HIRE_DATE_UNKNOWN = 0.0


def calculate_vacation_entitlement_days(hire_date: Optional[date], year: int) -> float:
    """Días de vacaciones que corresponden a `year` dado `hire_date`.

    Casos:
    - `hire_date is None` -> `FALLBACK_DAYS_WHEN_HIRE_DATE_UNKNOWN` (0).
    - `hire_date.year > year` -> el contrato todavía no había empezado ese
      año -> 0.
    - `hire_date.year < year` -> año completo trabajado -> 20.
    - `hire_date.year == year` -> meses completos trabajados = los que van
      desde el mes de alta hasta diciembre, ambos inclusive.
    """
    if hire_date is None:
        return FALLBACK_DAYS_WHEN_HIRE_DATE_UNKNOWN

    if hire_date.year > year:
        return 0.0

    if hire_date.year < year:
        months_worked = 12
    else:
        months_worked = 12 - hire_date.month + 1

    semesters = months_worked // MONTHS_PER_SEMESTER
    return float(DAYS_PER_SEMESTER * semesters)


def resolve_vacation_entitlement_days(
    *, hire_date: Optional[date], vacation_days_override: Optional[float], year: int
) -> float:
    """Fuente única para resolver el entitlement efectivo de un año: el
    override manual del admin manda si está fijado (no NULL); si no hay
    override, se calcula automáticamente desde `hire_date`."""
    if vacation_days_override is not None:
        return float(vacation_days_override)
    return calculate_vacation_entitlement_days(hire_date, year)
