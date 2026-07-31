BEGIN;

-- Historial de cambios de rol (RF-A10.6). Hasta ahora un cambio de rol era
-- DESTRUCTIVO: `update_staff_member` hace `role_id = COALESCE($5, role_id)` y el
-- valor anterior se perdía sin rastro más allá de `users.updated_at`, que además
-- se pisa en cualquier otra edición. No había ninguna tabla de auditoría en las
-- 38 migraciones previas.
--
-- POR QUÉ HACE FALTA para el pedido "que se guarde su antigüedad": la antigüedad
-- laboral ya estaba a salvo — `users.hire_date` NO forma parte del `UPDATE` del
-- PATCH, así que es inmutable tras el alta y el cálculo de vacaciones
-- (`absences/domain/vacation_entitlement.py`) sigue saliendo igual. Lo que no
-- existía es saber DESDE CUÁNDO alguien fue becario y desde cuándo es
-- trabajador, que es la pregunta que RRHH va a hacer el día que un becario
-- promocione. Eso no se puede reconstruir de `users`: hay que registrarlo cuando
-- ocurre.
CREATE TABLE IF NOT EXISTS user_role_history (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- NULL = alta inicial (no venía de ningún rol previo).
    from_role_id UUID REFERENCES roles(id) ON DELETE RESTRICT,
    to_role_id   UUID NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    -- NULLABLE a propósito, y NO por comodidad: las filas sembradas más abajo
    -- para la plantilla que ya existe no siempre pueden saber quién dio de alta
    -- a quién (el primer admin se sembró directo en `users`, sin invitación —
    -- ver 007_seed_initial_admin.sql). NULL dice "no consta", que es la verdad;
    -- un `changed_by` inventado apuntando a Beatriz habría dejado una auditoría
    -- que miente.
    changed_by   UUID REFERENCES users(id) ON DELETE SET NULL,
    changed_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    note         TEXT
);

CREATE INDEX IF NOT EXISTS idx_user_role_history_user
    ON user_role_history(user_id, changed_at DESC);

-- Fila de alta para la plantilla que YA existe, para que el historial no arranque
-- vacío y la ficha no muestre "sin datos" a todo el mundo. `changed_at` es la
-- fecha real de creación del usuario, no la de esta migración.
--
-- `invited_by` de la invitación cuando exista (es la mejor fuente de "quién lo
-- dio de alta"); NULL para quien entró sin invitación. Se toma la invitación más
-- antigua por email: reenviar una invitación crea filas nuevas y la última no
-- dice quién hizo el alta original.
INSERT INTO user_role_history (user_id, from_role_id, to_role_id, changed_by, changed_at, note)
SELECT u.id,
       NULL,
       u.role_id,
       (
           SELECT i.invited_by
           FROM invitations i
           WHERE lower(i.email) = lower(u.email)
           ORDER BY i.created_at ASC
           LIMIT 1
       ),
       u.created_at,
       'Alta inicial (fila reconstruida al crear el historial de roles)'
FROM users u
WHERE u.deleted_at IS NULL
  -- Idempotente: si esta migración ya corrió, no duplica.
  AND NOT EXISTS (
      SELECT 1 FROM user_role_history h WHERE h.user_id = u.id
  );

COMMIT;
