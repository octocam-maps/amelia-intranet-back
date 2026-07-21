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

Los 4 roles son los del alcance actual del producto — el "Supervisor" que
sugerían las referencias visuales NO entra, RRHH lo descartó.
"""

from enum import Enum


class RoleCode(str, Enum):  # noqa: UP042 — mixin deliberado, ver docstring
    ADMINISTRADOR = "administrador"
    EMPLEADO = "empleado"
    EXTERNO_INVITADO = "externo_invitado"
    SOCIO = "socio"


ALL_ROLES = (
    RoleCode.ADMINISTRADOR,
    RoleCode.EMPLEADO,
    RoleCode.EXTERNO_INVITADO,
    RoleCode.SOCIO,
)

# Onboarding completo (5 pasos) / features de uso interno — excluye al
# externo-invitado, que tiene alcance parcial (solo vídeo + manual).
INTERNAL_ROLES = (RoleCode.ADMINISTRADOR, RoleCode.EMPLEADO, RoleCode.SOCIO)

ADMIN_ONLY = (RoleCode.ADMINISTRADOR,)

# Calendario general de la plantilla (LOTE 4): visión de RRHH del
# administrador + `socio` [migración 024], sin el resto de permisos de
# "Administración".
ADMIN_SOCIO = (RoleCode.ADMINISTRADOR, RoleCode.SOCIO)
