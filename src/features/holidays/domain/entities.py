"""Entidad de dominio del feature `holidays` (calendario laboral,
docs/permisos-roles.md § "Festivos" — el admin los marca anualmente; el
resto de la plantilla los ve en su calendario de ausencias). Sin
dependencias de framework/SQL."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


@dataclass(frozen=True)
class Holiday:
    id: str
    day: date
    name: str
    # `None` == aplica a las 3 entidades (hub/lab/ops) — `holidays.entity_id`
    # es NULLABLE con ese significado (003_hr_core.sql).
    entity_id: Optional[str]
    entity_code: Optional[str]
    created_at: datetime
    updated_at: datetime
