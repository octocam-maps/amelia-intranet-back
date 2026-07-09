"""
Entidades de dominio del feature `team`. Son proyecciones de SOLO LECTURA
sobre `users`/`user_profiles`/`entities` (directorio) y `absence_requests`
(calendario de vacaciones) — este feature nunca escribe; el alta/edición de
plantilla sigue siendo responsabilidad exclusiva de Administración (Fase 5,
parte de gestión) y de `absences`.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class TeamMember:
    """Fila del directorio. Campos SEGUROS de cara al RGPD: nunca incluye
    `dni_nif`, `iban`, `address`, `social_security_number` ni `birth_date`
    (esos viven en `user_profiles` pero no salen de este feature)."""

    id: str
    full_name: str
    job_title: Optional[str]
    entity_code: Optional[str]
    entity_name: Optional[str]
    phone: Optional[str]
    email: str
    avatar_url: Optional[str]


@dataclass(frozen=True)
class VacationCalendarEntry:
    """Tramo de vacaciones APROBADAS de un miembro del equipo, para pintar
    el calendario mensual — nunca ausencias pendientes/rechazadas de otros
    tipos (baja médica, asuntos propios): eso sería un dato sensible de
    cara al resto de la plantilla."""

    user_id: str
    full_name: str
    start_date: date
    end_date: date
