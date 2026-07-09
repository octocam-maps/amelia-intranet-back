"""Fake en memoria de `IStaffRepository` — permite testear los casos de
uso sin Postgres, igual que en `features/absences` y `features/team`."""

import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Optional

from src.features.staff.domain.entities import StaffMember

_ENTITIES = {"hub": "entity-hub", "lab": "entity-lab", "ops": "entity-ops"}
_ROLES = {
    "administrador": "role-administrador",
    "empleado": "role-empleado",
    "externo_invitado": "role-externo_invitado",
}


class FakeStaffRepository:
    def __init__(self, members: Optional[list[StaffMember]] = None):
        self.members: dict[str, StaffMember] = {m.id: m for m in (members or [])}
        self.departments: dict[tuple[str, str], str] = {}

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
        vacation_days_per_year,
    ) -> StaffMember:
        entity_code = next((code for code, eid in _ENTITIES.items() if eid == entity_id), None)
        role_code = next((code for code, rid in _ROLES.items() if rid == role_id), None)
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
            vacation_days_per_year=vacation_days_per_year,
            created_at=datetime.now(timezone.utc),
        )
        self.members[member.id] = member
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
        vacation_days_per_year,
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

        updated = replace(
            existing,
            job_title=job_title if job_title is not None else existing.job_title,
            department_id=department_id if department_id is not None else existing.department_id,
            entity_id=entity_id if entity_id is not None else existing.entity_id,
            entity_code=entity_code,
            role_id=role_id if role_id is not None else existing.role_id,
            role_code=role_code,
            vacation_days_per_year=(
                vacation_days_per_year
                if vacation_days_per_year is not None
                else existing.vacation_days_per_year
            ),
            status=status if status is not None else existing.status,
        )
        self.members[user_id] = updated
        return updated
