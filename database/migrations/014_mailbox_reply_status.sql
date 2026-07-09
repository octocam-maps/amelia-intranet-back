BEGIN;

-- Fase 6 (buzón anónimo, recepción del admin): el admin necesita poder
-- responder al emisor SIN romper el anonimato — la respuesta se guarda en
-- el propio mensaje (visible por `reference_code`, nunca vinculada a un
-- user_id) y se añade el estado `resolved` para el filtro de la bandeja
-- (`?status=unread|all|resolved`, docs/deck-fase6/12-buzon-recepcion-admin.png).
ALTER TABLE anonymous_messages
    ADD COLUMN IF NOT EXISTS admin_reply TEXT,
    ADD COLUMN IF NOT EXISTS replied_at  TIMESTAMPTZ;

-- `archived` no lo escribía ningún endpoint todavía — se sustituye por
-- `resolved`, el estado real que pide el mockup. La tabla está vacía en
-- todos los entornos actuales, así que no hay filas que migrar.
ALTER TABLE anonymous_messages
    DROP CONSTRAINT IF EXISTS anonymous_messages_status_check;
ALTER TABLE anonymous_messages
    ADD CONSTRAINT anonymous_messages_status_check
    CHECK (status IN ('new', 'read', 'resolved'));

-- `category` no tenía CHECK en 005_admin_comms.sql (quedó como texto libre
-- a falta de definir las categorías de producto) — Fase 6 las fija a las 3
-- del formulario de envío (docs/deck-fase6/13-buzon-empleado.png).
ALTER TABLE anonymous_messages
    ADD CONSTRAINT anonymous_messages_category_check
    CHECK (category IN ('sugerencia', 'consulta', 'incidencia'));

COMMIT;
