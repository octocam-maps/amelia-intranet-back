"""
Entidades de dominio del feature `team`. Son proyecciones de SOLO LECTURA
sobre `users`/`user_profiles`/`entities` (directorio) y `absence_requests`
(calendario de vacaciones) — este feature nunca escribe; el alta/edición de
plantilla sigue siendo responsabilidad exclusiva de Administración (Fase 5,
parte de gestión) y de `absences`.
"""

from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional

# Kind privacy-safe expuesto por el calendario de equipo. El backend MAPEA
# el `absence_types.code` real a uno de estos 3 valores y nunca propaga el
# code crudo — `baja_medica`/`duelo`/`asuntos_propios`/`justificada`/`otros`
# caen todos en "ausente" para no exponer datos sensibles (salud, motivos
# personales → categoría especial RGPD) al resto de la plantilla.
AbsenceKind = Literal["vacaciones", "remoto", "ausente"]


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
class TeamBirthday:
    """Cumpleaños de un empleado interno dentro de la ventana consultada
    (widget "Cumpleaños esta semana" del Inicio). Por RGPD NUNCA expone el
    año de nacimiento (no debe poder derivarse la edad de nadie desde este
    endpoint): solo `day`/`month`, sin `birth_date` completo. Solo plantilla
    interna (`is_external = FALSE`): los externos-invitado no forman parte
    de este widget."""

    user_id: str
    full_name: str
    avatar_url: Optional[str]
    day: int
    month: int
    is_today: bool


@dataclass(frozen=True)
class TeamAbsenceEntry:
    """Tramo de ausencia APROBADA de un compañero del MISMO departamento que
    el solicitante, para pintar el calendario mensual del equipo — nunca
    ausencias pendientes/rechazadas, y nunca de otros departamentos.

    `kind` es SIEMPRE uno de `AbsenceKind` (nunca el `code` real del tipo de
    ausencia): `vacaciones` y `remoto` se muestran tal cual, y CUALQUIER
    otro tipo (baja médica, asuntos propios, justificada, duelo, otros...)
    se colapsa en `ausente` — ese mapeo ocurre en el repositorio/SQL, nunca
    aquí ni en infrastructure/routes, así que el dato sensible jamás sale
    de la capa de persistencia."""

    user_id: str
    full_name: str
    start_date: date
    end_date: date
    kind: AbsenceKind
