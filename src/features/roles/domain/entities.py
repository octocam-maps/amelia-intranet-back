"""
Entidad de dominio del feature `roles`. Proyección de SOLO LECTURA sobre la
tabla `roles` (001_core_identity.sql + 024_socio_role.sql) — este feature
nunca escribe: los roles son datos de sistema (`is_system = TRUE` en las 4
filas actuales), no un CRUD de producto.

Es la FUENTE ÚNICA de "qué roles existen" para el resto del backend: los
casos de uso que necesitan validar un `role_code` asignable (staff,
announcements) ya resuelven contra la misma tabla vía su propio
`resolve_role_id` — este feature solo expone la enumeración completa para
poblar selectores (p.ej. `StaffForm` en el frontend).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Role:
    id: str
    code: str
    name: str
