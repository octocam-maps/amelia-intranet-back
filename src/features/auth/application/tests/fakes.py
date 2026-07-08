"""
Fakes en memoria de los puertos de `auth` (`IUserRepository`,
`ISessionRepository`, `IGoogleIdentityVerifier`, `IJWTService`). Permiten
testear los casos de uso sin Postgres ni credenciales reales de Google —
esa es la ganancia de haberlos modelado como Protocols en `domain/ports.py`.
"""

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.features.auth.domain.entities import AuthenticatedUser, PendingInvitation, SessionRecord


@dataclass
class FakeGoogleIdentity:
    sub: str
    email: str
    email_verified: bool
    full_name: str
    avatar_url: Optional[str]
    hosted_domain: Optional[str]
    is_internal: bool


class FakeGoogleVerifier:
    def __init__(self, identity: FakeGoogleIdentity):
        self.identity = identity

    def verify(self, id_token_str: str) -> FakeGoogleIdentity:
        return self.identity


class FakeJWTService:
    """
    Codifica el payload en el propio string del token (sin firmar de
    verdad) para que `verify_token` pueda "decodificarlo" de vuelta sin
    depender de `jose`/secretos — suficiente para probar la lógica de los
    casos de uso, que es lo único que estos tests cubren.
    """

    access_token_expire_minutes = 15

    def create_access_token(self, data, expires_delta=None):
        return f"access:{data['sub']}"

    def create_refresh_token(self, data, expires_delta=None):
        jti = data.get("jti", str(uuid.uuid4()))
        return f"refresh:{data['sub']}:{jti}"

    def verify_token(self, token: str) -> dict:
        parts = token.split(":")
        if parts[0] == "refresh":
            return {"sub": parts[1], "jti": parts[2], "type": "refresh"}
        return {"sub": parts[1], "type": "access"}

    def get_refresh_token_expires_at(self) -> datetime:
        return datetime.now(timezone.utc) + timedelta(days=7)


class FakeSessionRepository:
    def __init__(self):
        self.sessions: dict[str, dict] = {}

    async def create_session(self, *, user_id, jti, family_id, expires_at, user_agent, ip_address):
        self.sessions[jti] = {"user_id": user_id, "family_id": family_id, "revoked": False}

    async def find_session(self, jti: str) -> Optional[SessionRecord]:
        session = self.sessions.get(jti)
        if session is None:
            return None
        return SessionRecord(
            id=jti,
            user_id=session["user_id"],
            jti=jti,
            family_id=session["family_id"],
            is_revoked=session["revoked"],
        )

    async def revoke_session(self, jti: str) -> None:
        if jti in self.sessions:
            self.sessions[jti]["revoked"] = True

    async def revoke_family(self, family_id: str) -> int:
        count = 0
        for session in self.sessions.values():
            if session["family_id"] == family_id and not session["revoked"]:
                session["revoked"] = True
                count += 1
        return count

    async def revoke_all_sessions_for_user(self, user_id: str) -> int:
        count = 0
        for session in self.sessions.values():
            if session["user_id"] == user_id and not session["revoked"]:
                session["revoked"] = True
                count += 1
        return count


class FakeUserRepository:
    def __init__(self, users=None, invitations=None):
        self.users: dict[str, AuthenticatedUser] = {u.id: u for u in (users or [])}
        self.invitations: dict[str, PendingInvitation] = {i.email: i for i in (invitations or [])}
        self._google_sub_by_user_id: dict[str, str] = {}
        self.bound_calls: list[str] = []

    async def find_by_google_sub(self, google_sub: str) -> Optional[AuthenticatedUser]:
        for user_id, sub in self._google_sub_by_user_id.items():
            if sub == google_sub:
                return self.users.get(user_id)
        return None

    async def find_by_email(self, email: str) -> Optional[AuthenticatedUser]:
        email = email.lower()
        for user in self.users.values():
            if user.email == email:
                return user
        return None

    async def find_by_id(self, user_id: str) -> Optional[AuthenticatedUser]:
        return self.users.get(user_id)

    async def find_pending_invitation(self, email: str) -> Optional[PendingInvitation]:
        return self.invitations.get(email.lower())

    async def create_user_from_invitation(
        self, invitation: PendingInvitation, *, google_sub, full_name, avatar_url, hosted_domain
    ) -> AuthenticatedUser:
        user_id = str(uuid.uuid4())
        user = AuthenticatedUser(
            id=user_id,
            email=invitation.email,
            full_name=full_name,
            avatar_url=avatar_url,
            role_code=invitation.role_code,
            role_id=invitation.role_id,
            entity_id=invitation.entity_id,
            department_id=None,
            manager_id=None,
            job_title=None,
            status="active",
            is_external=invitation.role_code == "externo_invitado",
        )
        self.users[user_id] = user
        self._google_sub_by_user_id[user_id] = google_sub
        self.invitations.pop(invitation.email, None)
        return user

    async def create_auto_provisioned_user(
        self, email: str, *, google_sub, full_name, avatar_url, hosted_domain
    ) -> AuthenticatedUser:
        user_id = str(uuid.uuid4())
        user = AuthenticatedUser(
            id=user_id,
            email=email.lower(),
            full_name=full_name,
            avatar_url=avatar_url,
            role_code="empleado",
            role_id="role-empleado",
            entity_id=None,
            department_id=None,
            manager_id=None,
            job_title=None,
            status="active",
            is_external=False,
        )
        self.users[user_id] = user
        self._google_sub_by_user_id[user_id] = google_sub
        return user

    async def bind_google_login(
        self, user_id: str, *, google_sub, full_name, avatar_url, hosted_domain
    ) -> None:
        self.bound_calls.append(user_id)
        self._google_sub_by_user_id[user_id] = google_sub
        existing = self.users[user_id]
        new_status = "active" if existing.status == "invited" else existing.status
        self.users[user_id] = replace(
            existing,
            full_name=full_name,
            avatar_url=avatar_url or existing.avatar_url,
            status=new_status,
        )
