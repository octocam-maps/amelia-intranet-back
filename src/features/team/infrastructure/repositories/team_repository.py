"""
Adaptador asyncpg del puerto `ITeamRepository`. SQL crudo de SOLO LECTURA
sobre tablas de otros features — ver la nota de diseño en
`domain/entities.py`. No hay ningún INSERT/UPDATE/DELETE en este archivo.
"""

import calendar
from datetime import date, timedelta
from typing import Optional

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool

from ...domain.entities import TeamAbsenceEntry, TeamBirthday, TeamMember
from ...domain.ports import ITeamRepository

# Únicos `absence_types.code` que se muestran con su etiqueta real en el
# calendario de equipo. CUALQUIER otro code (baja_medica, asuntos_propios,
# justificada, duelo, otros...) cae en "ausente" vía el `ELSE` del `CASE` de
# `list_team_absences` — nunca se añade aquí un code nuevo para "destaparlo"
# sin decidirlo explícitamente (son datos sensibles / categoría especial RGPD).
_PUBLIC_ABSENCE_KINDS = ("vacaciones", "remoto")


class PostgresTeamRepository(ITeamRepository):
    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    async def list_directory(self) -> list[TeamMember]:
        rows = await self._db.fetch(
            """
            SELECT u.id, u.full_name, u.job_title, u.email, u.avatar_url,
                   e.code AS entity_code, e.name AS entity_name,
                   p.phone
            FROM users u
            LEFT JOIN entities e ON e.id = u.entity_id
            LEFT JOIN user_profiles p ON p.user_id = u.id
            WHERE u.status != 'suspended' AND u.deleted_at IS NULL
            ORDER BY u.full_name ASC
            """
        )
        return [
            TeamMember(
                id=str(row["id"]),
                full_name=row["full_name"],
                job_title=row["job_title"],
                entity_code=row["entity_code"],
                entity_name=row["entity_name"],
                phone=row["phone"],
                email=row["email"],
                avatar_url=row["avatar_url"],
            )
            for row in rows
        ]

    async def get_department_id(self, user_id: str) -> Optional[str]:
        row = await self._db.fetchrow(
            """
            SELECT department_id
            FROM users
            WHERE id = $1::uuid AND deleted_at IS NULL
            """,
            user_id,
        )
        if row is None or row["department_id"] is None:
            return None
        return str(row["department_id"])

    async def list_team_absences(
        self, *, department_id: str, year: int, month: int
    ) -> list[TeamAbsenceEntry]:
        first_day = date(year, month, 1)
        last_day = date(year, month, calendar.monthrange(year, month)[1])
        rows = await self._db.fetch(
            """
            SELECT r.user_id, u.full_name, r.start_date, r.end_date,
                   CASE t.code
                       WHEN 'vacaciones' THEN 'vacaciones'
                       WHEN 'remoto' THEN 'remoto'
                       ELSE 'ausente'
                   END AS kind
            FROM absence_requests r
            JOIN users u ON u.id = r.user_id
            JOIN absence_types t ON t.id = r.absence_type_id
            WHERE r.status = 'approved'
              AND u.department_id = $1::uuid
              AND r.start_date <= $3 AND r.end_date >= $2
            ORDER BY r.start_date ASC
            """,
            department_id,
            first_day,
            last_day,
        )
        # El `CASE` de la query ya garantiza `kind ∈ {vacaciones, remoto,
        # ausente}` — este `if` es una segunda barrera (defensa en
        # profundidad) para que, si algún día alguien añade un `WHEN` nuevo
        # en el SQL sin darse cuenta de la implicación RGPD, el `code` crudo
        # siga sin poder llegar al DTO/cliente.
        return [
            TeamAbsenceEntry(
                user_id=str(row["user_id"]),
                full_name=row["full_name"],
                start_date=row["start_date"],
                end_date=row["end_date"],
                kind=row["kind"] if row["kind"] in _PUBLIC_ABSENCE_KINDS else "ausente",
            )
            for row in rows
        ]

    async def list_upcoming_birthdays(self, *, today: date, days: int) -> list[TeamBirthday]:
        # Ventana de "mes-día" candidatos generada en Python (no en SQL) para
        # que el wrap de fin de año (p.ej. 29-dic + 7 días -> incluye 1-4 de
        # enero) sea trivial: sumar días a `today` ya rueda el año solo.
        offset_by_key: dict[str, int] = {}
        candidates: list[str] = []
        for offset in range(days):
            candidate = today + timedelta(days=offset)
            key = f"{candidate.month:02d}-{candidate.day:02d}"
            candidates.append(key)
            offset_by_key.setdefault(key, offset)

        rows = await self._db.fetch(
            """
            SELECT u.id, u.full_name, u.avatar_url, p.birth_date
            FROM users u
            JOIN user_profiles p ON p.user_id = u.id
            WHERE u.is_external = FALSE
              AND u.status != 'suspended'
              AND u.deleted_at IS NULL
              AND p.birth_date IS NOT NULL
              AND to_char(p.birth_date, 'MM-DD') = ANY($1::text[])
            """,
            candidates,
        )

        entries = [
            TeamBirthday(
                user_id=str(row["id"]),
                full_name=row["full_name"],
                avatar_url=row["avatar_url"],
                day=row["birth_date"].day,
                month=row["birth_date"].month,
                is_today=offset_by_key[f"{row['birth_date'].month:02d}-{row['birth_date'].day:02d}"] == 0,
            )
            for row in rows
        ]
        entries.sort(key=lambda e: (offset_by_key[f"{e.month:02d}-{e.day:02d}"], e.full_name))
        return entries
