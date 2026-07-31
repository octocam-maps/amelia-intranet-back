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

Los 5 roles son los del alcance actual del producto — el "Supervisor" que
sugerían las referencias visuales NO entra, RRHH lo descartó.
"""

from enum import Enum


class RoleCode(str, Enum):  # noqa: UP042 — mixin deliberado, ver docstring
    ADMINISTRADOR = "administrador"
    EMPLEADO = "empleado"
    EXTERNO_INVITADO = "externo_invitado"
    SOCIO = "socio"
    BECARIO = "becario"


ALL_ROLES = (
    RoleCode.ADMINISTRADOR,
    RoleCode.EMPLEADO,
    RoleCode.EXTERNO_INVITADO,
    RoleCode.SOCIO,
    RoleCode.BECARIO,
)

# Onboarding completo (5 pasos) / features de uso interno — excluye al
# externo-invitado, que tiene alcance parcial (solo vídeo + manual).
#
# `becario` SÍ entra [migración 038]: accede a todo lo que ve un empleado. Se
# añade aquí, y no endpoint a endpoint, para que las features futuras le den
# acceso por defecto — un olvido debe dejarle DENTRO, que es el comportamiento
# pedido, no fuera en silencio. Lo único que se le niega es el fichaje, y eso
# se expresa restringiendo ahí (`TIME_CLOCK_ROLES`), no ampliando aquí.
INTERNAL_ROLES = (
    RoleCode.ADMINISTRADOR,
    RoleCode.EMPLEADO,
    RoleCode.SOCIO,
    RoleCode.BECARIO,
)

# Control horario (RF-A10): es `INTERNAL_ROLES` MENOS el becario. Existe como
# grupo propio porque "quién puede fichar" y "quién es de uso interno" dejaron
# de ser la misma pregunta al entrar el rol becario — antes de la migración 038
# ambas cosas eran `INTERNAL_ROLES` y esa coincidencia ocultaba que eran dos
# conceptos distintos.
#
# El externo-invitado ya estaba fuera (docs/permisos-roles.md: Control horario
# ❌ para externo). Un becario que no ficha tampoco debe recibir el recordatorio
# diario de fichaje — ver `list_active_user_ids_excluding_roles` en
# `notifications/infrastructure/repositories/notification_repository.py`.
TIME_CLOCK_ROLES = (RoleCode.ADMINISTRADOR, RoleCode.EMPLEADO, RoleCode.SOCIO)

# El complemento de `TIME_CLOCK_ROLES`, DERIVADO en vez de escrito a mano: quien
# no puede fichar tampoco debe recibir el recordatorio diario de fichaje
# (RF-A4.3). Si mañana entra un rol y no se le da acceso al fichaje, queda
# excluido del recordatorio automáticamente — dos listas paralelas escritas a
# mano se habrían desincronizado en el primer despiste, y el síntoma habría sido
# un email diario pidiéndole fichar a alguien que no tiene dónde hacerlo.
ROLES_WITHOUT_TIME_CLOCK = tuple(
    role for role in ALL_ROLES if role not in TIME_CLOCK_ROLES
)

ADMIN_ONLY = (RoleCode.ADMINISTRADOR,)

# Calendario general de la plantilla (LOTE 4): visión de RRHH del
# administrador + `socio` [migración 024], sin el resto de permisos de
# "Administración".
ADMIN_SOCIO = (RoleCode.ADMINISTRADOR, RoleCode.SOCIO)
