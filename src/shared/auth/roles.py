"""
Fuente única de verdad de los códigos de rol del producto (docs/permisos-roles.md).
Antes vivían duplicados como strings mágicos ("administrador", "empleado", ...)
en decenas de `require_role(...)` y comparaciones sueltas en casos de uso —
un typo en cualquiera de esas copias pasaba silenciosamente el guard
equivocado sin que nada lo detectara en tiempo de desarrollo.

`RoleCode` hereda de `str` a propósito: `user["role"]` (el payload del JWT)
siempre es un string plano, y las comparaciones (`==`, `in`) entre un
`RoleCode` y ese string funcionan sin cambios — así `require_role(*roles: str)`
(`src/shared/auth/dependencies.py:77`) sigue aceptando estas tuplas tal cual,
sin tocar su firma.

Los 6 roles son los del alcance actual del producto — el "Supervisor" que
sugerían las referencias visuales NO entra, RRHH lo descartó.
"""

from enum import Enum


class RoleCode(str, Enum):  # noqa: UP042 — mixin deliberado, ver docstring
    ADMINISTRADOR = "administrador"
    EMPLEADO = "empleado"
    EXTERNO_INVITADO = "externo_invitado"
    SOCIO = "socio"
    BECARIO = "becario"
    TECNICO = "tecnico"


ALL_ROLES = (
    RoleCode.ADMINISTRADOR,
    RoleCode.EMPLEADO,
    RoleCode.EXTERNO_INVITADO,
    RoleCode.SOCIO,
    RoleCode.BECARIO,
    RoleCode.TECNICO,
)

# Onboarding completo (5 pasos) / features de uso interno — excluye al
# externo-invitado, que tiene alcance parcial (solo vídeo + manual).
#
# `becario` SÍ entra [migración 038]: accede a todo lo que ve un empleado. Se
# añade aquí, y no endpoint a endpoint, para que las features futuras le den
# acceso por defecto — un olvido debe dejarle DENTRO, que es el comportamiento
# pedido, no fuera en silencio. Lo único que se le niega es el fichaje, y eso
# se expresa restringiendo ahí (`TIME_CLOCK_ROLES`), no ampliando aquí.
#
# `tecnico` SÍ entra [migración 051] por el mismo motivo: accede a todo lo que
# ve un empleado. Lo único que cambia en él es CÓMO registra su jornada, y eso
# se expresa más abajo, no recortando aquí.
INTERNAL_ROLES = (
    RoleCode.ADMINISTRADOR,
    RoleCode.EMPLEADO,
    RoleCode.SOCIO,
    RoleCode.BECARIO,
    RoleCode.TECNICO,
)

# Control horario (RF-A10): es `INTERNAL_ROLES` MENOS el becario. Existe como
# grupo propio porque "quién puede fichar" y "quién es de uso interno" dejaron
# de ser la misma pregunta al entrar el rol becario — antes de la migración 038
# ambas cosas eran `INTERNAL_ROLES` y esa coincidencia ocultaba que eran dos
# conceptos distintos.
#
# El externo-invitado ya estaba fuera (docs/permisos-roles.md: Control horario
# ❌ para externo). El `tecnico` [migración 051] tampoco entra: no ficha por
# tramos, cumplimenta un parte diario (`TECHNICIAN_ROLES`).
TIME_CLOCK_ROLES = (RoleCode.ADMINISTRADOR, RoleCode.EMPLEADO, RoleCode.SOCIO)

# Parte diario del técnico (requerimiento v1.2 §M1): proyecto, lugar, horario,
# pausa, pernocta y categoría de producto, uno por día, con bolsa mensual de
# 162 h. Guarda los endpoints de `/time-clock/technician-logs`.
TECHNICIAN_ROLES = (RoleCode.TECNICO,)

# Quién debe DEJAR CONSTANCIA DE SU JORNADA cada día, sea por el fichaje de
# tramos o por el parte del técnico. No es lo mismo que `TIME_CLOCK_ROLES`, y
# confundirlos tiene consecuencias: el recordatorio diario (RF-A4.3) se deriva
# de este grupo, así que si se hubiera derivado del fichaje, el técnico —a quien
# el parte le es OBLIGATORIO a diario— habría dejado de recibirlo en silencio.
DAILY_TIME_LOG_ROLES = TIME_CLOCK_ROLES + TECHNICIAN_ROLES

# El complemento de `DAILY_TIME_LOG_ROLES`, DERIVADO en vez de escrito a mano:
# quien no tiene dónde registrar su jornada no debe recibir el recordatorio
# diario (RF-A4.3). Si mañana entra un rol y no se le da ninguna forma de
# registrar jornada, queda excluido del recordatorio automáticamente — dos
# listas paralelas escritas a mano se habrían desincronizado en el primer
# despiste, y el síntoma habría sido un email diario pidiéndole fichar a alguien
# que no tiene dónde hacerlo.
ROLES_WITHOUT_TIME_TRACKING = tuple(
    role for role in ALL_ROLES if role not in DAILY_TIME_LOG_ROLES
)

ADMIN_ONLY = (RoleCode.ADMINISTRADOR,)

# Calendario general de la plantilla (LOTE 4): visión de RRHH del
# administrador + `socio` [migración 024], sin el resto de permisos de
# "Administración".
ADMIN_SOCIO = (RoleCode.ADMINISTRADOR, RoleCode.SOCIO)
