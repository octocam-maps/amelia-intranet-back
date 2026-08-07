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
from src.features.staff.domain.entities import RoleChange, StaffMember
from src.shared.email.domain.entities import EmailResult


def _current_year() -> int:
    return datetime.now(timezone.utc).year

_DEFAULT_INVITED_BY = "admin-1"

# Las CUATRO sociedades. `hincator` se añadió el 2026-07-29 (migración 036):
# sin ella aquí, cualquier test que dé de alta a una de las 19 personas de esa
# sociedad recibe un InvalidEntityCodeError que no refleja la realidad.
_ENTITIES = {
    "hub": "entity-hub",
    "lab": "entity-lab",
    "ops": "entity-ops",
    "hincator": "entity-hincator",
}
_ROLES = {
    "administrador": "role-administrador",
    "empleado": "role-empleado",
    "externo_invitado": "role-externo_invitado",
    "socio": "role-socio",
    # [038] Debe reflejar la tabla `roles` real: sin esta entrada, el fake
    # rechaza `becario` con `InvalidRoleCodeError` y los tests de promoción
    # fallarían por el motivo equivocado.
    "becario": "role-becario",
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
        # Filas que el repositorio real escribiría en `user_role_history` (039).
        self.role_history: list[dict] = []
        # Baja definitiva: ids marcados como borrados. La fila sigue en
        # `members`, igual que en BD sigue en `users`.
        self.deleted_member_ids: set[str] = set()

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

    async def count_active_admins(self, *, excluding_user_id: Optional[str] = None) -> int:
        return sum(
            1
            for m in self.members.values()
            if m.role_code == "administrador"
            and m.status == "active"
            and m.id != excluding_user_id
            and m.id not in self.deleted_member_ids
        )

    async def soft_delete_member(self, user_id: str) -> None:
        """Refleja lo que hace el adaptador real: la fila NO se borra, se
        marca. Guardar los ids aparte —en vez de sacarlos de `members`— es lo
        que permite comprobar en los tests que el histórico sigue ahí."""
        self.deleted_member_ids.add(user_id)

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
        contract_type=None,
        clear_contract_type=False,
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
            contract_type=contract_type,
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
        # Fila de alta del historial de roles (039), igual que
        # `PostgresStaffRepository.create_staff_member`.
        self.role_history.append(
            {
                "user_id": member.id,
                "from_role_id": None,
                "to_role_id": role_id,
                "changed_by": invited_by,
            }
        )
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

    async def list_role_history(self, user_id: str) -> list[RoleChange]:
        _CODES_BY_ID = {rid: code for code, rid in _ROLES.items()}
        rows = [r for r in self.role_history if r["user_id"] == user_id]
        return [
            RoleChange(
                id=f"history-{index}",
                from_role_code=(
                    _CODES_BY_ID.get(row["from_role_id"])
                    if row["from_role_id"] is not None
                    else None
                ),
                to_role_code=_CODES_BY_ID.get(row["to_role_id"], "?"),
                changed_by_id=row["changed_by"],
                changed_by_name=None,
                changed_at=datetime(2026, 7, 31, 12, index, tzinfo=timezone.utc),
                note=None,
            )
            # Más reciente primero, igual que el `ORDER BY changed_at DESC` real.
            for index, row in reversed(list(enumerate(rows)))
        ]

    async def update_staff_member(
        self,
        user_id,
        *,
        job_title,
        contract_type=None,
        clear_contract_type=False,
        department_id,
        entity_id,
        role_id,
        is_external,
        vacation_days_override,
        clear_vacation_days_override,
        status,
        hire_date=None,
        changed_by=None,
    ) -> Optional[StaffMember]:
        existing = self.members.get(user_id)
        if existing is None:
            return None

        # Traza de cambio de rol (039), igual que el repositorio real: solo
        # cuando el rol cambia de verdad. Se expone para que los tests puedan
        # afirmar sobre ella sin un Postgres delante.
        if role_id is not None and role_id != existing.role_id:
            self.role_history.append(
                {
                    "user_id": user_id,
                    "from_role_id": existing.role_id,
                    "to_role_id": role_id,
                    "changed_by": changed_by,
                }
            )

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

        # `hire_date`: COALESCE, igual que el repositorio real — `None` deja la
        # que estaba, nunca la vacía.
        new_hire_date = hire_date if hire_date is not None else existing.hire_date

        # El saldo se recalcula si cambió algo de lo que depende: el override o
        # la fecha de alta.
        entitlement_touched = (
            clear_vacation_days_override
            or vacation_days_override is not None
            or hire_date is not None
        )
        year = _current_year()
        new_vacation_days_per_year = (
            resolve_vacation_entitlement_days(
                hire_date=new_hire_date, vacation_days_override=new_override, year=year
            )
            if entitlement_touched
            else existing.vacation_days_per_year
        )

        updated = replace(
            existing,
            job_title=job_title if job_title is not None else existing.job_title,
            contract_type=(
                None
                if clear_contract_type
                else (contract_type if contract_type is not None else existing.contract_type)
            ),
            department_id=department_id if department_id is not None else existing.department_id,
            entity_id=entity_id if entity_id is not None else existing.entity_id,
            entity_code=entity_code,
            role_id=role_id if role_id is not None else existing.role_id,
            role_code=role_code,
            hire_date=new_hire_date,
            vacation_days_override=new_override,
            vacation_days_per_year=new_vacation_days_per_year,
            status=status if status is not None else existing.status,
        )
        self.members[user_id] = updated
        return updated


class FakeSessionRevoker:
    """Doble en memoria de `ISessionRevoker` (defensa en profundidad de
    AUTHN-2) — registra las llamadas para poder aseverar que suspender
    revoca sesiones y que cualquier otra edición NO lo hace."""

    def __init__(self):
        self.revoked_user_ids: list[str] = []

    async def revoke_all_sessions_for_user(self, user_id: str) -> int:
        self.revoked_user_ids.append(user_id)
        return 1


class FakeDriveFolderProvisioner:
    """Doble en memoria de `IDriveFolderProvisioner` (puerto de
    `staff.domain.ports`, mismo patrón que `ISessionRevoker`/`FakeSessionRevoker`)
    — registra las llamadas para poder aseverar que el alta dispara el
    provisioning y que un fallo del proveedor de Drive NO revierte el alta
    (best-effort, mismo criterio que `FakeEmailSender.fail_for`)."""

    def __init__(self, *, fail_for: Optional[set[str]] = None):
        self.calls: list[tuple[str, str]] = []
        self._fail_for = fail_for or set()

    async def provision_folder(self, user_id: str, email: str) -> None:
        self.calls.append((user_id, email))
        if email in self._fail_for:
            raise RuntimeError(f"Simulated Drive failure for {email}")


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
