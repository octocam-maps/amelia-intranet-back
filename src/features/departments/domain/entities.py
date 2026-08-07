"""
Entidad de dominio del feature `departments`. Proyección de SOLO LECTURA
sobre la tabla `departments` (001_core_identity.sql + 016_departments_unique_name.sql)
— este feature nunca escribe: el alta/edición de departamentos hoy ocurre de
forma implícita desde `staff` (`get_or_create_department_id`, alta de
plantilla) o directamente en BD; no hay CRUD de producto para
`departments` (ver comentario en `016_departments_unique_name.sql`).

Es la FUENTE ÚNICA de "qué departamentos existen" para poblar selectores —
hoy, el Paso 5 del onboarding ("Completar perfil", RF §3.5) en el frontend.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Department:
    id: str
    name: str
    entity_id: str
    entity_code: Optional[str]
    # Catálogo 2026 (migración 054): `Software` y `Hardware` cuelgan de
    # `Producto`. El selector los agrupa bajo su padre en vez de mostrar
    # siete opciones planas donde tres son en realidad una rama.
    parent_department_id: Optional[str] = None
    parent_name: Optional[str] = None
