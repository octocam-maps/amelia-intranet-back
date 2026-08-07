"""
Adaptador asyncpg del puerto `IStaffRepository`. SQL crudo — sin ORM.
Único lugar del feature que conoce el esquema de `users`, `roles`,
`entities`, `departments` y (para el entitlement de vacaciones)
`absence_types`/`absence_balances`. `create_staff_member` además escribe en
`invitations` (001_core_identity.sql) — mismo acoplamiento cross-feature
que ya tiene `auth.user_repository` (`create_user_from_invitation`).

El cálculo automático del entitlement de vacaciones (`resolve_vacation_entitlement_days`,
`users.hire_date` + override manual en `users.vacation_days_override`,
027_users_vacation_days_override.sql) vive en el dominio de `absences` — se
importa aquí igual que ya se cruzaba a sus tablas por SQL crudo.
"""

import secrets
from datetime import date, datetime
from typing import Optional

from src.features.absences.domain.vacation_entitlement import (
    resolve_vacation_entitlement_days,
)
from src.shared.database.infrastructure.asyncpg_pool import DatabasePool
from src.shared.utils.timezone import today_in_madrid

from ...domain.entities import RoleChange, StaffMember
from ...domain.ports import IStaffRepository

_STAFF_SELECT = """
    SELECT
        u.id, u.full_name, u.email, u.avatar_url, u.job_title, u.contract_type,
        u.status, u.hire_date, u.created_at,
        u.vacation_days_override,
        u.department_id, d.name AS department_name,
        u.entity_id, e.code AS entity_code,
        u.role_id, r.code AS role_code,
        ab.entitled_days AS vacation_days_per_year
    FROM users u
    JOIN roles r ON r.id = u.role_id
    LEFT JOIN entities e ON e.id = u.entity_id
    LEFT JOIN departments d ON d.id = u.department_id
    -- El entitlement de vacaciones vive en `absence_balances` (Fase 3), no
    -- en `users` — se toma el saldo del año en curso del tipo `vacaciones`.
    LEFT JOIN absence_types abt ON abt.code = 'vacaciones'
    LEFT JOIN absence_balances ab
        ON ab.user_id = u.id AND ab.absence_type_id = abt.id
        AND ab.year = EXTRACT(YEAR FROM CURRENT_DATE)::int
    WHERE u.deleted_at IS NULL
"""

# Upsert del entitlement anual — mismo patrón de "no-op upsert" que
# `absence_repository.get_or_create_balance`, pero aquí SÍ sobreescribe
# `entitled_days`: se llama SIEMPRE que se crea/edita una persona (calculado
# o con override, ver `_resolve_current_year_entitled_days`), no solo cuando
# el admin escribe un número a mano.
_UPSERT_VACATION_BALANCE = """
    INSERT INTO absence_balances (user_id, absence_type_id, year, entitled_days)
    SELECT $1, id, EXTRACT(YEAR FROM CURRENT_DATE)::int, $2
    FROM absence_types WHERE code = 'vacaciones'
    ON CONFLICT (user_id, absence_type_id, year)
    DO UPDATE SET entitled_days = EXCLUDED.entitled_days, updated_at = CURRENT_TIMESTAMP
"""


def _row_to_member(row) -> StaffMember:
    vacation_days = row["vacation_days_per_year"]
    override = row["vacation_days_override"]
    return StaffMember(
        id=str(row["id"]),
        full_name=row["full_name"],
        email=row["email"],
        avatar_url=row["avatar_url"],
        job_title=row["job_title"],
        contract_type=row["contract_type"],
        department_id=str(row["department_id"]) if row["department_id"] else None,
        department_name=row["department_name"],
        entity_id=str(row["entity_id"]) if row["entity_id"] else None,
        entity_code=row["entity_code"],
        role_id=str(row["role_id"]),
        role_code=row["role_code"],
        status=row["status"],
        hire_date=row["hire_date"],
        vacation_days_per_year=float(vacation_days) if vacation_days is not None else None,
        vacation_days_override=float(override) if override is not None else None,
        vacation_days_calculated=resolve_vacation_entitlement_days(
            hire_date=row["hire_date"],
            vacation_days_override=None,  # queremos el cálculo puro, no el override
            year=today_in_madrid().year,
        ),
        created_at=row["created_at"],
    )


class PostgresStaffRepository(IStaffRepository):
    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    def _filtered_query(self, *, entity_code: Optional[str], search: Optional[str]):
        query = _STAFF_SELECT
        params: list = []
        if entity_code:
            params.append(entity_code)
            query += f" AND e.code = ${len(params)}"
        if search:
            params.append(f"%{search}%")
            query += f" AND u.full_name ILIKE ${len(params)}"
        return query, params

    async def list_staff(
        self,
        *,
        entity_code: Optional[str],
        search: Optional[str],
        page: int,
        page_size: int,
    ) -> list[StaffMember]:
        query, params = self._filtered_query(entity_code=entity_code, search=search)
        params.extend([page_size, (page - 1) * page_size])
        query += f" ORDER BY u.full_name LIMIT ${len(params) - 1} OFFSET ${len(params)}"
        rows = await self._db.fetch(query, *params)
        return [_row_to_member(row) for row in rows]

    async def count_staff(self, *, entity_code: Optional[str], search: Optional[str]) -> int:
        filter_sql = ""
        params: list = []
        if entity_code:
            params.append(entity_code)
            filter_sql += f" AND e.code = ${len(params)}"
        if search:
            params.append(f"%{search}%")
            filter_sql += f" AND u.full_name ILIKE ${len(params)}"
        query = f"""
            SELECT COUNT(*) FROM users u
            LEFT JOIN entities e ON e.id = u.entity_id
            WHERE u.deleted_at IS NULL {filter_sql}
        """
        return await self._db.fetchval(query, *params)

    async def find_by_id(self, user_id: str) -> Optional[StaffMember]:
        row = await self._db.fetchrow(f"{_STAFF_SELECT} AND u.id = $1", user_id)
        return _row_to_member(row) if row else None

    async def find_by_email(self, email: str) -> Optional[StaffMember]:
        row = await self._db.fetchrow(f"{_STAFF_SELECT} AND u.email = $1", email)
        return _row_to_member(row) if row else None

    async def resolve_entity_id(self, entity_code: str) -> Optional[str]:
        row = await self._db.fetchval("SELECT id FROM entities WHERE code = $1", entity_code)
        return str(row) if row else None

    async def resolve_role_id(self, role_code: str) -> Optional[str]:
        row = await self._db.fetchval("SELECT id FROM roles WHERE code = $1", role_code)
        return str(row) if row else None

    async def get_or_create_department_id(self, *, entity_id: str, department_name: str) -> str:
        row = await self._db.fetchrow(
            """
            INSERT INTO departments (entity_id, name)
            VALUES ($1, $2)
            ON CONFLICT (entity_id, name) DO UPDATE SET updated_at = departments.updated_at
            RETURNING id
            """,
            entity_id,
            department_name,
        )
        return str(row["id"])

    async def create_staff_member(
        self,
        *,
        full_name: str,
        email: str,
        job_title: Optional[str],
        contract_type: Optional[str] = None,
        department_id: Optional[str],
        entity_id: str,
        role_id: str,
        is_external: bool,
        hire_date: Optional[date],
        vacation_days_override: Optional[float],
        invited_by: str,
        expires_at: datetime,
    ) -> StaffMember:
        async with self._db.acquire() as connection:
            async with connection.transaction():
                user_id = await connection.fetchval(
                    """
                    INSERT INTO users (
                        full_name, email, job_title, contract_type, department_id,
                        entity_id, role_id, is_external, hire_date,
                        vacation_days_override, status
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 'invited')
                    RETURNING id
                    """,
                    full_name,
                    email,
                    job_title,
                    contract_type,
                    department_id,
                    entity_id,
                    role_id,
                    is_external,
                    hire_date,
                    vacation_days_override,
                )
                # Se siembra SIEMPRE (calculado o con override) — a
                # diferencia del comportamiento previo (solo si el admin
                # escribía un número), así el contador nunca queda en blanco
                # hasta la primera lectura lazy.
                entitled_days = resolve_vacation_entitlement_days(
                    hire_date=hire_date,
                    vacation_days_override=vacation_days_override,
                    year=today_in_madrid().year,
                )
                await connection.execute(_UPSERT_VACATION_BALANCE, user_id, entitled_days)
                # Traza de la invitación (feature `invitations`: listar
                # pendientes/reenviar/cancelar). `token` NO se usa en ningún
                # enlace hoy — el acceso sigue siendo 100% Google OIDC, solo
                # satisface el `NOT NULL UNIQUE` del esquema y deja la puerta
                # abierta a un magic-link futuro sin migración.
                await connection.execute(
                    """
                    INSERT INTO invitations (email, role_id, entity_id, token, invited_by, expires_at)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    email,
                    role_id,
                    entity_id,
                    secrets.token_urlsafe(32),
                    invited_by,
                    expires_at,
                )
                # Fila de alta del historial de roles (039), con
                # `from_role_id = NULL` = "no venía de ningún rol previo". Se
                # escribe aquí y no al promocionar por primera vez para que el
                # historial de una persona sea completo desde el alta: sin esta
                # fila, la ficha de quien nunca cambió de rol saldría vacía y no
                # se distinguiría de un fallo de carga.
                await connection.execute(
                    """
                    INSERT INTO user_role_history
                        (user_id, from_role_id, to_role_id, changed_by)
                    VALUES ($1, NULL, $2, $3)
                    """,
                    user_id,
                    role_id,
                    invited_by,
                )

        member = await self.find_by_id(str(user_id))
        assert member is not None
        return member

    async def update_staff_member(
        self,
        user_id: str,
        *,
        job_title: Optional[str],
        department_id: Optional[str],
        entity_id: Optional[str],
        role_id: Optional[str],
        is_external: Optional[bool],
        vacation_days_override: Optional[float],
        clear_vacation_days_override: bool,
        status: Optional[str],
        contract_type: Optional[str] = None,
        clear_contract_type: bool = False,
        hire_date: Optional[date] = None,
        changed_by: Optional[str] = None,
    ) -> Optional[StaffMember]:
        async with self._db.acquire() as connection:
            async with connection.transaction():
                # COALESCE: cada parámetro en NULL deja la columna como
                # estaba — semántica PATCH (actualización parcial).
                #
                # DOS excepciones, y por el mismo motivo: necesitan distinguir
                # "no tocar" de "vaciar", y un solo `None` no puede expresar las
                # dos cosas. Se resuelven con un flag booleano y un `CASE WHEN`
                # (mismo patrón que `holidays.update_holiday`/`clear_entity`):
                #   · `vacation_days_override` ($8/$9)
                #   · `contract_type` ($10/$11)
                #
                # `contract_type` llegó tarde a esta query y ES IMPORTANTE
                # recordar por qué: estuvo en la firma del método sin estar en el
                # `SET`, así que el PATCH respondía 200 y no guardaba nada. Si
                # añades otro campo, comprueba que aparece en los TRES sitios —
                # firma, `SET` y lista de parámetros— y escribe el test antes.
                #
                # `RETURNING hire_date, vacation_days_override` deja recalcular
                # el saldo sin una segunda ida y vuelta a `users`.
                # `prev` captura el rol ANTERIOR en el mismo statement que lo
                # pisa (039_user_role_history.sql). Leerlo con un SELECT suelto
                # antes del UPDATE también funcionaría dentro de esta
                # transacción, pero así no hay dos fuentes de "cuál era el rol
                # viejo" que puedan discrepar, ni un viaje extra.
                row = await connection.fetchrow(
                    """
                    UPDATE users
                    SET job_title = COALESCE($2, job_title),
                        department_id = COALESCE($3, department_id),
                        entity_id = COALESCE($4, entity_id),
                        role_id = COALESCE($5, role_id),
                        is_external = COALESCE($6, is_external),
                        status = COALESCE($7, status),
                        vacation_days_override = CASE
                            WHEN $8 THEN NULL
                            ELSE COALESCE($9, vacation_days_override)
                        END,
                        contract_type = CASE
                            WHEN $10 THEN NULL
                            ELSE COALESCE($11, contract_type)
                        END,
                        hire_date = COALESCE($12, hire_date),
                        updated_at = CURRENT_TIMESTAMP
                    FROM (
                        SELECT role_id AS previous_role_id FROM users WHERE id = $1
                    ) AS prev
                    WHERE users.id = $1 AND users.deleted_at IS NULL
                    RETURNING users.id, users.hire_date, users.vacation_days_override,
                              users.role_id, prev.previous_role_id
                    """,
                    user_id,
                    job_title,
                    department_id,
                    entity_id,
                    role_id,
                    is_external,
                    status,
                    clear_vacation_days_override,
                    vacation_days_override,
                    clear_contract_type,
                    contract_type,
                    hire_date,
                )
                if row is None:
                    return None

                # Traza del cambio de rol (RF-A10.6), en ESTA transacción: si el
                # UPDATE se revierte, el historial no queda contando un cambio
                # que no ocurrió. Solo se escribe cuando el rol cambió de verdad
                # — una edición de puesto o de entidad no debe generar una fila
                # de "cambio de rol" con el mismo rol a los dos lados.
                previous_role_id = row["previous_role_id"]
                if previous_role_id != row["role_id"]:
                    await connection.execute(
                        """
                        INSERT INTO user_role_history
                            (user_id, from_role_id, to_role_id, changed_by)
                        VALUES ($1, $2, $3, $4)
                        """,
                        user_id,
                        previous_role_id,
                        row["role_id"],
                        changed_by,
                    )

                # Solo se recalcula/reescribe el saldo cuando cambió algo de lo
                # que DEPENDE el entitlement en esta misma petición: el override
                # (fijado o vaciado) o la fecha de alta. Una edición no
                # relacionada (p. ej. solo el puesto) no debe tocar
                # `absence_balances` de rebote.
                #
                # `hire_date` entra aquí desde el 2026-08-03, y no es opcional:
                # `get_or_create_balance` calcula el entitlement UNA VEZ, al
                # crear la fila (su `ON CONFLICT` es un no-op deliberado). Sin
                # este recálculo, rellenar la fecha de alta de quien la tenía
                # vacía guardaría la fecha y dejaría el saldo en los 0 días con
                # que nació — el PATCH respondería 200 sin arreglar nada.
                if (
                    clear_vacation_days_override
                    or vacation_days_override is not None
                    or hire_date is not None
                ):
                    new_override = (
                        float(row["vacation_days_override"])
                        if row["vacation_days_override"] is not None
                        else None
                    )
                    entitled_days = resolve_vacation_entitlement_days(
                        hire_date=row["hire_date"],
                        vacation_days_override=new_override,
                        year=today_in_madrid().year,
                    )
                    await connection.execute(
                        _UPSERT_VACATION_BALANCE, user_id, entitled_days
                    )

        return await self.find_by_id(user_id)

    async def list_role_history(self, user_id: str) -> list[RoleChange]:
        # Se resuelven los CODES de rol y el NOMBRE del autor aquí, en la misma
        # query, en vez de devolver ids crudos: son tres `LEFT JOIN` sobre
        # tablas pequeñísimas, y la alternativa sería que el frontend cruzara
        # `GET /roles` y `GET /staff` para pintar una línea de texto.
        #
        # LEFT JOIN y no JOIN en los tres: `from_role_id` es NULL en el alta, y
        # `changed_by` es NULL cuando no consta (filas reconstruidas por la
        # migración 039, o un autor borrado -> `ON DELETE SET NULL`). Con un JOIN
        # normal, justo esas filas desaparecerían del historial en silencio.
        rows = await self._db.fetch(
            """
            SELECT h.id,
                   from_role.code AS from_role_code,
                   to_role.code   AS to_role_code,
                   h.changed_by   AS changed_by_id,
                   author.full_name AS changed_by_name,
                   h.changed_at,
                   h.note
            FROM user_role_history h
            JOIN roles to_role        ON to_role.id = h.to_role_id
            LEFT JOIN roles from_role ON from_role.id = h.from_role_id
            LEFT JOIN users author    ON author.id = h.changed_by
            WHERE h.user_id = $1
            ORDER BY h.changed_at DESC, h.id DESC
            """,
            user_id,
        )
        return [
            RoleChange(
                id=str(row["id"]),
                from_role_code=row["from_role_code"],
                to_role_code=row["to_role_code"],
                changed_by_id=(
                    str(row["changed_by_id"])
                    if row["changed_by_id"] is not None
                    else None
                ),
                changed_by_name=row["changed_by_name"],
                changed_at=row["changed_at"],
                note=row["note"],
            )
            for row in rows
        ]

    # --- Baja definitiva (soft delete con anonimización) ---

    async def count_active_admins(self, *, excluding_user_id: Optional[str] = None) -> int:
        return await self._db.fetchval(
            """
            SELECT COUNT(*) FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE r.code = 'administrador'
              AND u.deleted_at IS NULL
              AND u.status = 'active'
              AND ($1::uuid IS NULL OR u.id <> $1::uuid)
            """,
            excluding_user_id,
        )

    async def soft_delete_member(self, user_id: str) -> None:
        # Las tres escrituras van en UNA transacción: un usuario marcado como
        # borrado pero con su DNI e IBAN todavía en `user_profiles` sería
        # justo el estado que esta operación existe para evitar, y nadie lo
        # notaría porque la ficha ya no se puede abrir.
        async with self._db.acquire() as connection:
            async with connection.transaction():
                # PRIMERO las invitaciones y con el email TODAVÍA original:
                # `invitations` no tiene `user_id`, se relaciona por email, así
                # que hacerlo después del renombrado no encontraría ninguna y
                # el enlace pendiente seguiría dando de alta a quien acabamos
                # de dar de baja.
                await connection.execute(
                    """
                    UPDATE invitations SET status = 'revoked'
                    WHERE status = 'pending'
                      AND email = (SELECT email FROM users WHERE id = $1)
                    """,
                    user_id,
                )

                # El email se LIBERA renombrándolo, no se borra: `users.email`
                # es NOT NULL y UNIQUE. El sufijo con el epoch permite dar de
                # baja dos veces al mismo email (reingreso y nueva salida) sin
                # colisionar consigo mismo.
                await connection.execute(
                    """
                    UPDATE users
                    SET deleted_at = CURRENT_TIMESTAMP,
                        status     = 'suspended',
                        email      = email || '.deleted.' ||
                                     EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::bigint,
                        -- `google_sub` a NULL o el login por Google seguiría
                        -- reconociéndolo y crearía sesión contra una ficha
                        -- borrada. Es UNIQUE, así que además bloquearía el
                        -- alta futura de esa misma cuenta de Google.
                        google_sub = NULL,
                        avatar_url = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = $1 AND deleted_at IS NULL
                    """,
                    user_id,
                )

                # Datos personales sin finalidad una vez la persona se va
                # (RGPD, minimización). `city` y `company_phone` caen también:
                # son datos de contacto, no registro laboral.
                await connection.execute(
                    """
                    UPDATE user_profiles
                    SET dni_nif = NULL,
                        birth_date = NULL,
                        phone = NULL,
                        address = NULL,
                        city = NULL,
                        company_phone = NULL,
                        emergency_contact_name = NULL,
                        emergency_contact_phone = NULL,
                        iban = NULL,
                        social_security_number = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = $1
                    """,
                    user_id,
                )
