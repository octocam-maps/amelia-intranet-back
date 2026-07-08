BEGIN;

-- Anuncios / comunicados (Fase 5).
CREATE TABLE IF NOT EXISTS announcements (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title        VARCHAR(200) NOT NULL,
    body         TEXT NOT NULL,
    author_id    UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    audience     VARCHAR(20) NOT NULL DEFAULT 'all'
                   CHECK (audience IN ('all', 'entity', 'role')),
    entity_id    UUID REFERENCES entities(id) ON DELETE CASCADE,  -- si audience='entity'
    role_id      UUID REFERENCES roles(id) ON DELETE CASCADE,     -- si audience='role'
    is_pinned    BOOLEAN NOT NULL DEFAULT FALSE,
    published_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at   TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS announcement_reads (
    announcement_id UUID NOT NULL REFERENCES announcements(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    read_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (announcement_id, user_id)
);

-- =====================================================================
-- BUZÓN ANÓNIMO — anonimato garantizado por DISEÑO.
-- NO hay user_id, ni author, ni FK, ni INET. IMPOSIBLE correlacionar
-- el mensaje con un usuario a nivel de esquema. El endpoint que inserta
-- aquí NO debe registrar IP ni logs con datos de request.
-- reference_code permite seguimiento anónimo sin revelar identidad.
-- =====================================================================
CREATE TABLE IF NOT EXISTS anonymous_messages (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    reference_code VARCHAR(12) NOT NULL UNIQUE,   -- código para que el emisor haga seguimiento
    category       VARCHAR(40),
    subject        VARCHAR(200),
    body           TEXT NOT NULL,
    status         VARCHAR(20) NOT NULL DEFAULT 'new'
                     CHECK (status IN ('new', 'read', 'archived')),
    admin_note     TEXT,                          -- nota interna del admin, NO respuesta al emisor
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_anonymous_messages_status ON anonymous_messages(status);

COMMIT;
