"""Fakes en memoria de `IStaffRepository`/`IEmailSender` — permiten testear
los casos de uso sin Postgres, igual que en `features/absences` y
`features/team` (y `features/notifications/application/tests/fakes.py`
para el patrón de `FakeEmailSender`)."""

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Optional

from src.features.absences.domain.vacation_entitlement import (
    calculate_vacation_entitlement_days,
    resolve_vacation_entitlement_days,
)
from src.features.staff.domain.entities import StaffMember
from src.shared.email.domain.entities import EmailResult


def _current_year() -> int:
    return datetime.now(timezone.utc).year

_DEFAULT_INVITED_BY = "admin-1"

_ENTITIES = {"hub": "entity-hub", "lab": "entity-lab", "ops": "entity-ops"}
_ROLES = {
    "administrador": "role-administrador",
    "empleado": "role-empleado",
    "externo_invitado": "role-externo_invitado",
    "socio": "role-socio",
}


@dataclass
class RecordedInvitation:
    """Lo que `FakeStaffRepository.create_staff_member` registra de la
    fila `invitations` que en Postgres se inserta en la MISMA transacción
    que `users` (ver `PostgresStaffRepository.create_staff_member`)."""

    email: str
    role_id: str
    entity_id: str
    invited_by: str
    expires_at: datetime


class FakeStaffRepository:
    def __init__(self, members: Optional[list[StaffMember]] = None):
        self.members: dict[str, StaffMember] = {m.id: m for m in (members or [])}
        self.departments: dict[tuple[str, str], str] = {}
        self.invitations: list[RecordedInvitation] = []

    def _filtered(self, *, entity_code: Optional[str], search: Optional[str]) -> list[StaffMember]:
        members = list(self.members.values())
        if entity_code:
            members = [m for m in members if m.entity_code == entity_code]
        if search:
            needle = search.lower()
            members = [m for m in members if needle in m.full_name.lower()]
        return sorted(members, key=lambda m: m.full_name)

    async def list_staff(
        self,
        *,
        entity_code: Optional[str],
        search: Optional[str],
        page: int,
        page_size: int,
    ) -> list[StaffMember]:
        members = self._filtered(entity_code=entity_code, search=search)
        start = (page - 1) * page_size
        return members[start : start + page_size]

    async def count_staff(self, *, entity_code: Optional[str], search: Optional[str]) -> int:
        return len(self._filtered(entity_code=entity_code, search=search))

    async def find_by_id(self, user_id: str) -> Optional[StaffMember]:
        return self.members.get(user_id)

    async def find_by_email(self, email: str) -> Optional[StaffMember]:
        for member in self.members.values():
            if member.email == email:
                return member
        return None

    async def resolve_entity_id(self, entity_code: str) -> Optional[str]:
        return _ENTITIES.get(entity_code)

    async def resolve_role_id(self, role_code: str) -> Optional[str]:
        return _ROLES.get(role_code)

    async def get_or_create_department_id(self, *, entity_id: str, department_name: str) -> str:
        key = (entity_id, department_name)
        if key not in self.departments:
            self.departments[key] = str(uuid.uuid4())
        return self.departments[key]

    async def create_staff_member(
        self,
        *,
        full_name,
        email,
        job_title,
        department_id,
        entity_id,
        role_id,
        is_external,
        hire_date,
        vacation_days_override,
        invited_by,
        expires_at,
    ) -> StaffMember:
        entity_code = next((code for code, eid in _ENTITIES.items() if eid == entity_id), None)
        role_code = next((code for code, rid in _ROLES.items() if rid == role_id), None)
        year = _current_year()
        # Mismo comportamiento que `PostgresStaffRepository.create_staff_member`:
        # el saldo se siembra SIEMPRE, calculado o con override.
        entitled_days = resolve_vacation_entitlement_days(
            hire_date=hire_date, vacation_days_override=vacation_days_override, year=year
        )
        member = StaffMember(
            id=str(uuid.uuid4()),
            full_name=full_name,
            email=email,
            avatar_url=None,
            job_title=job_title,
            department_id=department_id,
            department_name=None,
            entity_id=entity_id,
            entity_code=entity_code,
            role_id=role_id,
            role_code=role_code,
            status="invited",
            hire_date=hire_date,
            vacation_days_per_year=entitled_days,
            vacation_days_override=vacation_days_override,
            vacation_days_calculated=calculate_vacation_entitlement_days(hire_date, year),
            created_at=datetime.now(timezone.utc),
        )
        self.members[member.id] = member
        self.invitations.append(
            RecordedInvitation(
                email=email,
                role_id=role_id,
                entity_id=entity_id,
                invited_by=invited_by,
                expires_at=expires_at,
            )
        )
        return member

    async def update_staff_member(
        self,
        user_id,
        *,
        job_title,
        department_id,
        entity_id,
        role_id,
        is_external,
        vacation_days_override,
        clear_vacation_days_override,
        status,
    ) -> Optional[StaffMember]:
        existing = self.members.get(user_id)
        if existing is None:
            return None

        entity_code = existing.entity_code
        if entity_id is not None:
            entity_code = next((code for code, eid in _ENTITIES.items() if eid == entity_id), None)
        role_code = existing.role_code
        if role_id is not None:
            role_code = next((code for code, rid in _ROLES.items() if rid == role_id), None)

        # Mismo contrato tri-state que `PostgresStaffRepository.update_staff_member`:
        # `clear_vacation_days_override=True` vacía el override (vuelve a
        # automático); si no, `COALESCE` (no tocar si viene `None`).
        if clear_vacation_days_override:
            new_override = None
        elif vacation_days_override is not None:
            new_override = vacation_days_override
        else:
            new_override = existing.vacation_days_override

        override_touched = clear_vacation_days_override or vacation_days_override is not None
        new_hire_date = existing.hire_date
        year = _current_year()
        new_vacation_days_per_year = (
            resolve_vacation_entitlement_days(
                hire_date=new_hire_date, vacation_days_override=new_override, year=year
            )
            if override_touched
            else existing.vacation_days_per_year
        )

        updated = replace(
            existing,
            job_title=job_title if job_title is not None else existing.job_title,
            department_id=department_id if department_id is not None else existing.department_id,
            entity_id=entity_id if entity_id is not None else existing.entity_id,
            entity_code=entity_code,
            role_id=role_id if role_id is not None else existing.role_id,
            role_code=role_code,
            vacation_days_override=new_override,
            vacation_days_per_year=new_vacation_days_per_year,
            status=status if status is not None else existing.status,
        )
        self.members[user_id] = updated
        return updated


class FakeEmailSender:
    """Mismo patrón que `features/notifications/application/tests/fakes.py`
    — `fail_for` simula un proveedor caído para probar que el alta es
    best-effort respecto al aviso por email."""

    def __init__(self, *, fail_for: Optional[set[str]] = None):
        self.sent: list[dict[str, Any]] = []
        self._fail_for = fail_for or set()

    async def send(
        self,
        *,
        to: str,
        template: str,
        context: dict[str, Any],
        user_id: Optional[str] = None,
    ) -> EmailResult:
        if to in self._fail_for:
            raise RuntimeError(f"Simulated email failure for {to}")
        self.sent.append({"to": to, "template": template, "context": context, "user_id": user_id})
        return EmailResult(status="sent", provider_message_id=f"fake-{uuid.uuid4()}")


def build_create_staff_member_use_case(
    repository: "FakeStaffRepository",
    *,
    email_sender: Optional[FakeEmailSender] = None,
    invitation_expires_days: int = 7,
) -> "CreateStaffMemberUseCase":
    """Fábrica compartida por los tests de `staff` que necesitan sembrar
    personas vía `CreateStaffMemberUseCase` (p. ej. `test_list_staff.py`,
    `test_update_staff_member.py`) sin repetir en cada archivo los 2
    parámetros nuevos que sumó la traza de `invitations` (Área 1 del
    design `rh-invitaciones-iconos-limpieza`)."""
    from src.features.staff.application.use_cases.create_staff_member import (
        CreateStaffMemberUseCase,
    )

    return CreateStaffMemberUseCase(
        repository,
        email_sender or FakeEmailSender(),
        invitation_expires_days,
        "http://localhost:5173",
    )
