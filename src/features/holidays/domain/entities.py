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
    # Fase 6 R2 (018): 'oficial' == importado de la API oficial; 'manual' ==
    # añadido a mano por el admin. `scope` es informativo para la UI.
    source: str = "manual"
    scope: Optional[str] = None


@dataclass(frozen=True)
class OfficialHoliday:
    """Festivo oficial tal como lo entrega un proveedor externo (Nager.Date),
    ya normalizado y filtrado a lo que aplica en Barcelona (nacional España o
    autonómico Cataluña). Es un value object de entrada al import — no lleva
    id ni entity_id porque los oficiales aplican a todas las entidades."""

    day: date
    name: str
    scope: str  # 'nacional' | 'autonomico'


@dataclass(frozen=True)
class ImportSummary:
    """Resultado de una importación de festivos oficiales."""

    imported: int
    updated: int
    skipped: int
