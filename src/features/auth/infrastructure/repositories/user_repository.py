"""
Adaptador asyncpg del puerto `IUserRepository`. SQL crudo — sin ORM.
Único lugar del feature `auth` que conoce el esquema de `users`,
`roles`, `entities` e `invitations`.
"""

from typing import Optional

from src.shared.auth.roles import RoleCode
from src.shared.database.infrastructure.asyncpg_pool import DatabasePool

from ...domain.entities import AuthenticatedUser, PendingInvitation
from ...domain.ports import IUserRepository

_USER_SELECT = """
    SELECT u.id, u.email, u.full_name, u.avatar_url, u.role_id, r.code AS role_code,
           u.entity_id, u.department_id, u.manager_id, u.job_title, u.status,
           u.is_external
    FROM users u
    JOIN roles r ON r.id = u.role_id
    WHERE u.deleted_at IS NULL
"""


def _row_to_user(row) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=str(row["id"]),
        email=row["email"],
        full_name=row["full_name"],
        avatar_url=row["avatar_url"],
        role_code=row["role_code"],
        role_id=str(row["role_id"]),
        entity_id=str(row["entity_id"]) if row["entity_id"] else None,
        department_id=str(row["department_id"]) if row["department_id"] else None,
        manager_id=str(row["manager_id"]) if row["manager_id"] else None,
        job_title=row["job_title"],
        status=row["status"],
        is_external=row["is_external"],
    )


class PostgresUserRepository(IUserRepository):
    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    async def find_by_google_sub(self, google_sub: str) -> Optional[AuthenticatedUser]:
        row = await self._db.fetchrow(f"{_USER_SELECT} AND u.google_sub = $1", google_sub)
        return _row_to_user(row) if row else None

    async def find_by_email(self, email: str) -> Optional[AuthenticatedUser]:
        row = await self._db.fetchrow(f"{_USER_SELECT} AND u.email = $1", email.lower())
        return _row_to_user(row) if row else None

    async def find_by_id(self, user_id: str) -> Optional[AuthenticatedUser]:
        row = await self._db.fetchrow(f"{_USER_SELECT} AND u.id = $1", user_id)
        return _row_to_user(row) if row else None

    async def find_pending_invitation(self, email: str) -> Optional[PendingInvitation]:
        row = await self._db.fetchrow(
            """
            SELECT i.id, i.email, i.role_id, r.code AS role_code, i.entity_id
            FROM invitations i
            JOIN roles r ON r.id = i.role_id
            WHERE i.email = $1 AND i.status = 'pending' AND i.expires_at > CURRENT_TIMESTAMP
            ORDER BY i.created_at DESC
            LIMIT 1
            """,
            email.lower(),
        )
        if not row:
            return None
        return PendingInvitation(
            id=str(row["id"]),
            email=row["email"],
            role_id=str(row["role_id"]),
            role_code=row["role_code"],
            entity_id=str(row["entity_id"]) if row["entity_id"] else None,
        )

    async def create_user_from_invitation(
        self,
        invitation: PendingInvitation,
        *,
        google_sub: str,
        full_name: str,
        avatar_url: Optional[str],
        hosted_domain: Optional[str],
    ) -> AuthenticatedUser:
        is_external = invitation.role_code == RoleCode.EXTERNO_INVITADO

        async with self._db.acquire() as connection:
            async with connection.transaction():
                user_id = await connection.fetchval(
                    """
                    INSERT INTO users (
                        email, google_sub, hosted_domain, full_name, avatar_url,
                        role_id, entity_id, status, is_external, last_login_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, 'active', $8, CURRENT_TIMESTAMP)
                    RETURNING id
                    """,
                    invitation.email,
                    google_sub,
                    hosted_domain,
                    full_name,
                    avatar_url,
                    invitation.role_id,
                    invitation.entity_id,
                    is_external,
                )
                await connection.execute(
                    """
                    UPDATE invitations
                    SET status = 'accepted', accepted_at = CURRENT_TIMESTAMP
                    WHERE id = $1
                    """,
                    invitation.id,
                )

        user = await self.find_by_id(str(user_id))
        assert user is not None
        return user

    async def create_auto_provisioned_user(
        self,
        email: str,
        *,
        google_sub: str,
        full_name: str,
        avatar_url: Optional[str],
        hosted_domain: Optional[str],
    ) -> AuthenticatedUser:
        user_id = await self._db.fetchval(
            """
            INSERT INTO users (
                email, google_sub, hosted_domain, full_name, avatar_url,
                role_id, status, is_external, last_login_at
            )
            VALUES (
                $1, $2, $3, $4, $5,
                (SELECT id FROM roles WHERE code = $6),
                'active', FALSE, CURRENT_TIMESTAMP
            )
            RETURNING id
            """,
            email.lower(),
            google_sub,
            hosted_domain,
            full_name,
            avatar_url,
            RoleCode.EMPLEADO.value,
        )
        user = await self.find_by_id(str(user_id))
        assert user is not None
        return user

    async def bind_google_login(
        self,
        user_id: str,
        *,
        google_sub: str,
        full_name: str,
        avatar_url: Optional[str],
        hosted_domain: Optional[str],
    ) -> None:
        await self._db.execute(
            """
            UPDATE users
            SET google_sub = $2,
                hosted_domain = $3,
                full_name = $4,
                avatar_url = COALESCE($5, avatar_url),
                last_login_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP,
                status = CASE WHEN status = 'invited' THEN 'active' ELSE status END
            WHERE id = $1
            """,
            user_id,
            google_sub,
            hosted_domain,
            full_name,
            avatar_url,
        )
