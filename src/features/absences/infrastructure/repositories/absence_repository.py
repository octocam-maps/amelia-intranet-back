"""
Adaptador asyncpg del puerto `IAbsenceRepository`. SQL crudo — sin ORM.
Único lugar del feature que conoce el esquema de `absence_types`,
`absence_balances`, `absence_requests` y `holidays`.
"""

from datetime import date
from typing import Optional

from src.shared.database.infrastructure.asyncpg_pool import DatabasePool

from ...domain.entities import AbsenceBalance, AbsenceRequest, AbsenceType
from ...domain.ports import IAbsenceRepository


def _row_to_type(row) -> AbsenceType:
    return AbsenceType(
        id=str(row["id"]),
        code=row["code"],
        name=row["name"],
        is_paid=row["is_paid"],
        affects_balance=row["affects_balance"],
        default_entitled_days=float(row["default_entitled_days"]),
        color=row["color"],
        is_active=row["is_active"],
        requires_approval=row["requires_approval"],
        requires_justification=row["requires_justification"],
        max_days_per_year=row["max_days_per_year"],
    )


def _row_to_balance(row) -> AbsenceBalance:
    return AbsenceBalance(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        absence_type_id=str(row["absence_type_id"]),
        year=row["year"],
        entitled_days=float(row["entitled_days"]),
        used_days=float(row["used_days"]),
        pending_days=float(row["pending_days"]),
    )


def _row_to_request(row) -> AbsenceRequest:
    return AbsenceRequest(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        absence_type_id=str(row["absence_type_id"]),
        start_date=row["start_date"],
        end_date=row["end_date"],
        days_count=float(row["days_count"]),
        reason=row["reason"],
        status=row["status"],
        reviewed_by=str(row["reviewed_by"]) if row["reviewed_by"] else None,
        reviewed_at=row["reviewed_at"],
        review_note=row["review_note"],
        created_at=row["created_at"],
        # Solo presente cuando la query hizo JOIN con `users` (bandejas de
        # admin) — `.get()` evita un KeyError en el resto de queries (`SELECT *`).
        user_full_name=row.get("user_full_name"),
    )


class PostgresAbsenceRepository(IAbsenceRepository):
    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    async def list_types(self) -> list[AbsenceType]:
        rows = await self._db.fetch(
            "SELECT * FROM absence_types WHERE is_active = TRUE ORDER BY name"
        )
        return [_row_to_type(row) for row in rows]

    async def list_all_types(self) -> list[AbsenceType]:
        # Gestión del admin: incluye los desactivados, a diferencia de
        # `list_types` (que el empleado usa para elegir tipo al solicitar).
        rows = await self._db.fetch("SELECT * FROM absence_types ORDER BY name")
        return [_row_to_type(row) for row in rows]

    async def find_type_by_id(self, absence_type_id: str) -> Optional[AbsenceType]:
        row = await self._db.fetchrow("SELECT * FROM absence_types WHERE id = $1", absence_type_id)
        return _row_to_type(row) if row else None

    async def find_type_by_code(self, code: str) -> Optional[AbsenceType]:
        row = await self._db.fetchrow("SELECT * FROM absence_types WHERE code = $1", code)
        return _row_to_type(row) if row else None

    async def create_type(
        self,
        *,
        code: str,
        name: str,
        is_paid: bool,
        affects_balance: bool,
        default_entitled_days: float,
        color: Optional[str],
        requires_approval: bool = True,
        requires_justification: bool = False,
        max_days_per_year: Optional[int] = None,
    ) -> AbsenceType:
        row = await self._db.fetchrow(
            """
            INSERT INTO absence_types (
                code, name, is_paid, affects_balance, default_entitled_days, color,
                requires_approval, requires_justification, max_days_per_year
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
            """,
            code,
            name,
            is_paid,
            affects_balance,
            default_entitled_days,
            color,
            requires_approval,
            requires_justification,
            max_days_per_year,
        )
        return _row_to_type(row)

    async def update_type(
        self,
        absence_type_id: str,
        *,
        name: Optional[str],
        is_paid: Optional[bool],
        affects_balance: Optional[bool],
        default_entitled_days: Optional[float],
        color: Optional[str],
        is_active: Optional[bool],
        requires_approval: Optional[bool] = None,
        requires_justification: Optional[bool] = None,
        max_days_per_year: Optional[int] = None,
    ) -> Optional[AbsenceType]:
        row = await self._db.fetchrow(
            """
            UPDATE absence_types
            SET name = COALESCE($2, name),
                is_paid = COALESCE($3, is_paid),
                affects_balance = COALESCE($4, affects_balance),
                default_entitled_days = COALESCE($5, default_entitled_days),
                color = COALESCE($6, color),
                is_active = COALESCE($7, is_active),
                requires_approval = COALESCE($8, requires_approval),
                requires_justification = COALESCE($9, requires_justification),
                max_days_per_year = COALESCE($10, max_days_per_year),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $1
            RETURNING *
            """,
            absence_type_id,
            name,
            is_paid,
            affects_balance,
            default_entitled_days,
            color,
            is_active,
            requires_approval,
            requires_justification,
            max_days_per_year,
        )
        return _row_to_type(row) if row else None

    async def get_or_create_balance(
        self, user_id: str, absence_type_id: str, year: int
    ) -> AbsenceBalance:
        row = await self._db.fetchrow(
            """
            SELECT * FROM absence_balances
            WHERE user_id = $1 AND absence_type_id = $2 AND year = $3
            """,
            user_id,
            absence_type_id,
            year,
        )
        if row:
            return _row_to_balance(row)

        default_days = await self._db.fetchval(
            "SELECT default_entitled_days FROM absence_types WHERE id = $1", absence_type_id
        )
        # ON CONFLICT hace este upsert seguro ante una carrera con otra
        # petición concurrente que intente crear el mismo saldo a la vez
        # (misma unicidad que uq_balance_user_type_year en 003_hr_core).
        row = await self._db.fetchrow(
            """
            INSERT INTO absence_balances (user_id, absence_type_id, year, entitled_days)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id, absence_type_id, year)
            DO UPDATE SET updated_at = absence_balances.updated_at
            RETURNING *
            """,
            user_id,
            absence_type_id,
            year,
            default_days or 0,
        )
        return _row_to_balance(row)

    async def list_balances_for_user(self, user_id: str, year: int) -> list[AbsenceBalance]:
        rows = await self._db.fetch(
            """
            SELECT * FROM absence_balances
            WHERE user_id = $1 AND year = $2
            ORDER BY absence_type_id
            """,
            user_id,
            year,
        )
        return [_row_to_balance(row) for row in rows]

    async def adjust_balance(
        self,
        user_id: str,
        absence_type_id: str,
        year: int,
        *,
        used_delta: float,
        pending_delta: float,
    ) -> None:
        # UPDATE incondicional — solo lo usa `ReviewAbsenceRequestUseCase`
        # DESPUÉS de haber ganado el UPDATE...WHERE status='pending' atómico
        # (ver update_request_status_if_pending), así que aquí ya no hay
        # carrera posible: la fila de la solicitud está "reservada".
        await self._db.execute(
            """
            UPDATE absence_balances
            SET used_days = used_days + $4,
                pending_days = pending_days + $5,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = $1 AND absence_type_id = $2 AND year = $3
            """,
            user_id,
            absence_type_id,
            year,
            used_delta,
            pending_delta,
        )

    async def try_reserve_balance(
        self,
        user_id: str,
        absence_type_id: str,
        year: int,
        *,
        pending_delta: float,
    ) -> bool:
        # RACE-1 (auditoría QA Fase 3): reservar saldo al CREAR una solicitud
        # debe ser un único UPDATE condicionado al saldo disponible EN LA
        # PROPIA QUERY (no leer el saldo en Python y decidir aparte) — así
        # dos solicitudes concurrentes del mismo usuario/tipo/año no pueden
        # ambas leer "saldo suficiente" y las dos escribir un overdraft.
        # 0 filas afectadas == saldo insuficiente en el momento del commit.
        row = await self._db.fetchrow(
            """
            UPDATE absence_balances
            SET pending_days = pending_days + $4,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = $1 AND absence_type_id = $2 AND year = $3
              AND (entitled_days - used_days - pending_days) >= $4
            RETURNING id
            """,
            user_id,
            absence_type_id,
            year,
            pending_delta,
        )
        return row is not None

    async def create_request(
        self,
        *,
        user_id: str,
        absence_type_id: str,
        start_date: date,
        end_date: date,
        days_count: float,
        reason: Optional[str],
    ) -> AbsenceRequest:
        row = await self._db.fetchrow(
            """
            INSERT INTO absence_requests
                (user_id, absence_type_id, start_date, end_date, days_count, reason)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            user_id,
            absence_type_id,
            start_date,
            end_date,
            days_count,
            reason,
        )
        return _row_to_request(row)

    async def find_request_by_id(self, request_id: str) -> Optional[AbsenceRequest]:
        row = await self._db.fetchrow("SELECT * FROM absence_requests WHERE id = $1", request_id)
        return _row_to_request(row) if row else None

    async def list_requests_for_user(self, user_id: str) -> list[AbsenceRequest]:
        rows = await self._db.fetch(
            "SELECT * FROM absence_requests WHERE user_id = $1 ORDER BY created_at DESC",
            user_id,
        )
        return [_row_to_request(row) for row in rows]

    async def list_pending_requests(self) -> list[AbsenceRequest]:
        # JOIN con `users` para alimentar `user_full_name` — la bandeja de
        # aprobación del admin necesita el nombre real, no solo el user_id.
        rows = await self._db.fetch(
            """
            SELECT ar.*, u.full_name AS user_full_name
            FROM absence_requests ar
            JOIN users u ON u.id = ar.user_id
            WHERE ar.status = 'pending'
            ORDER BY ar.created_at ASC
            """
        )
        return [_row_to_request(row) for row in rows]

    async def list_all_requests(self) -> list[AbsenceRequest]:
        # Idem — el "Calendario de la plantilla" (gantt) del admin usa esta
        # query y antes caía a "Empleado #XXXX" para quien no apareciera en
        # la bandeja de pendientes.
        rows = await self._db.fetch(
            """
            SELECT ar.*, u.full_name AS user_full_name
            FROM absence_requests ar
            JOIN users u ON u.id = ar.user_id
            ORDER BY ar.start_date DESC
            """
        )
        return [_row_to_request(row) for row in rows]

    async def update_request_status_if_pending(
        self,
        request_id: str,
        *,
        status: str,
        reviewed_by: str,
        review_note: Optional[str],
    ) -> Optional[AbsenceRequest]:
        # RACE-2 (auditoría QA Fase 3): condicionar el UPDATE a
        # `status = 'pending'` en la misma query hace que, si dos admins (o
        # doble clic) revisan la misma solicitud a la vez, solo UNO de los
        # dos UPDATE afecte una fila — el otro ve 0 filas y sabe que ya no
        # tiene que ajustar el saldo. `None` == la solicitud ya no estaba
        # pending cuando esta query se ejecutó.
        row = await self._db.fetchrow(
            """
            UPDATE absence_requests
            SET status = $2, reviewed_by = $3, review_note = $4,
                reviewed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = $1 AND status = 'pending'
            RETURNING *
            """,
            request_id,
            status,
            reviewed_by,
            review_note,
        )
        return _row_to_request(row) if row else None

    async def list_holiday_dates(self, date_from: date, date_to: date) -> list[date]:
        rows = await self._db.fetch(
            "SELECT day FROM holidays WHERE day BETWEEN $1 AND $2", date_from, date_to
        )
        return [row["day"] for row in rows]
