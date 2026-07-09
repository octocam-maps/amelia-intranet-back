-- =============================================================================
-- init.sql — Esquema COMPLETO de la Amelia Intranet (estado actual, autocontenido).
--
-- Contiene la estructura de creación inline (no apunta a las migraciones), igual
-- que en backend2. Es la fuente para inicializar una base de datos NUEVA de un
-- solo golpe (servidor de hosting o Docker local): se monta como
-- `/docker-entrypoint-initdb.d/00_init.sql` en `docker-compose.local.yaml`.
--
-- Las migraciones de `database/migrations/NNN_*.sql` son el registro incremental
-- para bases YA existentes (se aplican a mano). Al añadir una migración nueva hay
-- que reflejar su cambio TAMBIÉN aquí (columna/tabla/seed en su estado final).
--
-- Idempotente: todo va con IF NOT EXISTS / ON CONFLICT DO NOTHING.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- btree_gist: necesario para el EXCLUDE anti-solape de `time_clock_entries`.
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- ----------------------------------------------------------------------------
-- Identidad y acceso (Fase 1)
-- ----------------------------------------------------------------------------

-- Entidades legales del grupo: Hub / Lab / Ops
CREATE TABLE IF NOT EXISTS entities (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code       VARCHAR(20) NOT NULL UNIQUE CHECK (code IN ('hub', 'lab', 'ops')),
    name       VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Roles del sistema (administrador / empleado / externo_invitado)
CREATE TABLE IF NOT EXISTS roles (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code       VARCHAR(30) NOT NULL UNIQUE
                 CHECK (code IN ('administrador', 'empleado', 'externo_invitado')),
    name       VARCHAR(80) NOT NULL,
    is_system  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Departamentos (jerárquicos) → base del organigrama (Fase 5).
-- UNIQUE(entity_id, name) [016]: permite el upsert "sobre la marcha" desde el
-- alta/edición de plantilla, sin CRUD propio de departamentos todavía.
CREATE TABLE IF NOT EXISTS departments (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id            UUID NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
    parent_department_id UUID REFERENCES departments(id) ON DELETE SET NULL,
    name                 VARCHAR(120) NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_departments_entity_name UNIQUE (entity_id, name)
);
CREATE INDEX IF NOT EXISTS idx_departments_entity_id ON departments(entity_id);

-- Usuarios. Identidad delegada en Google OIDC → sin password.
-- hire_date [015]: fecha de alta laboral, ligada al cálculo de vacaciones.
CREATE TABLE IF NOT EXISTS users (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email          VARCHAR(255) NOT NULL UNIQUE,          -- se normaliza a minúsculas en app
    google_sub     VARCHAR(255) UNIQUE,                   -- NULL hasta el primer login con Google
    hosted_domain  VARCHAR(255),                          -- claim hd (ameliahub.com para internos)
    full_name      VARCHAR(160) NOT NULL,
    avatar_url     TEXT,
    role_id        UUID NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    entity_id      UUID REFERENCES entities(id) ON DELETE SET NULL,       -- NULL para externo
    department_id  UUID REFERENCES departments(id) ON DELETE SET NULL,
    manager_id     UUID REFERENCES users(id) ON DELETE SET NULL,         -- línea de reporte (organigrama)
    job_title      VARCHAR(120),
    hire_date      DATE,
    status         VARCHAR(20) NOT NULL DEFAULT 'invited'
                     CHECK (status IN ('invited', 'active', 'suspended')),
    is_external    BOOLEAN NOT NULL DEFAULT FALSE,
    last_login_at  TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_users_role_id    ON users(role_id);
CREATE INDEX IF NOT EXISTS idx_users_entity_id  ON users(entity_id);
CREATE INDEX IF NOT EXISTS idx_users_manager_id ON users(manager_id);
CREATE INDEX IF NOT EXISTS idx_users_status     ON users(status);

-- Perfil RRHH (datos sensibles RGPD → cifrado en reposo recomendado).
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id                 UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    dni_nif                 VARCHAR(20),
    birth_date              DATE,
    phone                   VARCHAR(30),
    address                 TEXT,
    emergency_contact_name  VARCHAR(160),
    emergency_contact_phone VARCHAR(30),
    iban                    VARCHAR(34),                  -- para volcado de nóminas
    social_security_number  VARCHAR(30),
    completed_at            TIMESTAMPTZ,                  -- paso 5 del onboarding
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Invitaciones (alta de plantilla y de externos con Gmail personal).
CREATE TABLE IF NOT EXISTS invitations (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email       VARCHAR(255) NOT NULL,
    role_id     UUID NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    entity_id   UUID REFERENCES entities(id) ON DELETE SET NULL,
    token       VARCHAR(120) NOT NULL UNIQUE,
    invited_by  UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    status      VARCHAR(20) NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'accepted', 'revoked', 'expired')),
    expires_at  TIMESTAMPTZ NOT NULL,
    accepted_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_invitations_email  ON invitations(email);
CREATE INDEX IF NOT EXISTS idx_invitations_status ON invitations(status);

-- Sesiones de refresh token — revocación server-side + rotación OWASP.
-- family_id [009]: al detectar reuso de un jti revocado se revoca la familia.
CREATE TABLE IF NOT EXISTS auth_sessions (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    jti        VARCHAR(64) NOT NULL UNIQUE,
    family_id  UUID NOT NULL DEFAULT uuid_generate_v4(),
    issued_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    user_agent TEXT,
    ip_address INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id   ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_jti       ON auth_sessions(jti);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_family_id ON auth_sessions(family_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_active    ON auth_sessions(user_id) WHERE revoked_at IS NULL;

-- ----------------------------------------------------------------------------
-- Onboarding (Fase 2)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS onboarding_steps (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    step_order INTEGER NOT NULL UNIQUE,
    type       VARCHAR(20) NOT NULL
                 CHECK (type IN ('video', 'quiz', 'signature', 'manual', 'profile')),
    title      VARCHAR(160) NOT NULL,
    config     JSONB NOT NULL DEFAULT '{}',
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS onboarding_progress (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    step_id      UUID NOT NULL REFERENCES onboarding_steps(id) ON DELETE CASCADE,
    status       VARCHAR(20) NOT NULL DEFAULT 'locked'
                   CHECK (status IN ('locked', 'available', 'in_progress', 'completed')),
    progress_pct INTEGER NOT NULL DEFAULT 0 CHECK (progress_pct BETWEEN 0 AND 100),
    data         JSONB NOT NULL DEFAULT '{}',
    started_at   TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_onboarding_progress_user_step UNIQUE (user_id, step_id)
);
CREATE INDEX IF NOT EXISTS idx_onboarding_progress_user_id ON onboarding_progress(user_id);

-- Cuestionario: UN SOLO INTENTO garantizado por UNIQUE(user_id, step_id).
CREATE TABLE IF NOT EXISTS onboarding_quiz_attempts (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    step_id      UUID NOT NULL REFERENCES onboarding_steps(id) ON DELETE CASCADE,
    answers      JSONB NOT NULL,
    score        NUMERIC(5,2) NOT NULL,
    passed       BOOLEAN NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_quiz_attempt_single UNIQUE (user_id, step_id)
);

CREATE TABLE IF NOT EXISTS onboarding_documents (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    kind         VARCHAR(20) NOT NULL CHECK (kind IN ('signature', 'manual')),
    title        VARCHAR(200) NOT NULL,
    version      INTEGER NOT NULL DEFAULT 1,
    content_hash VARCHAR(64) NOT NULL,       -- SHA-256 del documento vigente
    storage_ref  TEXT,
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Firma digital trazable (paso 3): fecha/hora + IP + hash del documento firmado.
CREATE TABLE IF NOT EXISTS document_signatures (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id           UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    document_id       UUID NOT NULL REFERENCES onboarding_documents(id) ON DELETE RESTRICT,
    document_version  INTEGER NOT NULL,
    document_hash     VARCHAR(64) NOT NULL,
    signature_hash    VARCHAR(128) NOT NULL,
    signed_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address        INET NOT NULL,
    user_agent        TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_signature_user_doc_version UNIQUE (user_id, document_id, document_version)
);
CREATE INDEX IF NOT EXISTS idx_document_signatures_user_id ON document_signatures(user_id);

CREATE TABLE IF NOT EXISTS document_acknowledgements (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_id     UUID NOT NULL REFERENCES onboarding_documents(id) ON DELETE RESTRICT,
    acknowledged_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address      INET,
    CONSTRAINT uq_ack_user_doc UNIQUE (user_id, document_id)
);

-- ----------------------------------------------------------------------------
-- RRHH core: control horario, ausencias, festivos (Fase 3 / Fase 6 R2)
-- ----------------------------------------------------------------------------

-- EXCLUDE anti-solape [012]: dos tramos del mismo usuario/día no pueden
-- solaparse en el tiempo (un tramo abierto llega hasta 'infinity').
CREATE TABLE IF NOT EXISTS time_clock_entries (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    work_date  DATE NOT NULL,
    clock_in   TIMESTAMPTZ NOT NULL,
    clock_out  TIMESTAMPTZ,                  -- NULL = jornada abierta
    source     VARCHAR(20) NOT NULL DEFAULT 'web' CHECK (source IN ('web', 'mobile')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT time_clock_entries_no_overlap EXCLUDE USING gist (
        user_id WITH =,
        work_date WITH =,
        tstzrange(clock_in, COALESCE(clock_out, 'infinity'::timestamptz), '[)') WITH &&
    )
);
CREATE INDEX IF NOT EXISTS idx_time_clock_entries_user_date ON time_clock_entries(user_id, work_date);

CREATE TABLE IF NOT EXISTS time_clock_breaks (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entry_id    UUID NOT NULL REFERENCES time_clock_entries(id) ON DELETE CASCADE,
    break_start TIMESTAMPTZ NOT NULL,
    break_end   TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_time_clock_breaks_entry_id ON time_clock_breaks(entry_id);

-- Tipos de ausencia (configurable). default_entitled_days [010];
-- requires_approval / requires_justification / max_days_per_year [019].
CREATE TABLE IF NOT EXISTS absence_types (
    id                     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code                   VARCHAR(40) NOT NULL UNIQUE,
    name                   VARCHAR(120) NOT NULL,
    is_paid                BOOLEAN NOT NULL DEFAULT TRUE,
    affects_balance        BOOLEAN NOT NULL DEFAULT TRUE,
    default_entitled_days  NUMERIC(5,1) NOT NULL DEFAULT 0,
    color                  VARCHAR(9),
    is_active              BOOLEAN NOT NULL DEFAULT TRUE,
    requires_approval      BOOLEAN NOT NULL DEFAULT TRUE,
    requires_justification BOOLEAN NOT NULL DEFAULT FALSE,
    max_days_per_year      INTEGER CHECK (max_days_per_year IS NULL OR max_days_per_year >= 0),
    created_at             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS absence_balances (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    absence_type_id UUID NOT NULL REFERENCES absence_types(id) ON DELETE CASCADE,
    year            INTEGER NOT NULL,
    entitled_days   NUMERIC(5,1) NOT NULL DEFAULT 0,
    used_days       NUMERIC(5,1) NOT NULL DEFAULT 0,
    pending_days    NUMERIC(5,1) NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_balance_user_type_year UNIQUE (user_id, absence_type_id, year)
);

CREATE TABLE IF NOT EXISTS absence_requests (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    absence_type_id UUID NOT NULL REFERENCES absence_types(id) ON DELETE RESTRICT,
    start_date      DATE NOT NULL,
    end_date        DATE NOT NULL,
    days_count      NUMERIC(5,1) NOT NULL,
    reason          TEXT,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled')),
    reviewed_by     UUID REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at     TIMESTAMPTZ,
    review_note     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (end_date >= start_date)
);
CREATE INDEX IF NOT EXISTS idx_absence_requests_user_id ON absence_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_absence_requests_status  ON absence_requests(status);
CREATE INDEX IF NOT EXISTS idx_absence_requests_dates   ON absence_requests(start_date, end_date);

-- Festivos. updated_at [017]; source (oficial/manual) + scope [018].
CREATE TABLE IF NOT EXISTS holidays (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    day        DATE NOT NULL,
    name       VARCHAR(120) NOT NULL,
    entity_id  UUID REFERENCES entities(id) ON DELETE CASCADE,   -- NULL = aplica a todas
    source     TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('oficial', 'manual')),
    scope      TEXT CHECK (scope IN ('nacional', 'autonomico', 'local', 'empresa')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_holiday_day_entity UNIQUE (day, entity_id)
);

-- ----------------------------------------------------------------------------
-- Documentos + Drive (Fase 4)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS employee_documents (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,   -- dueño
    category      VARCHAR(20) NOT NULL
                    CHECK (category IN ('payslip', 'contract', 'general', 'other')),
    title         VARCHAR(200) NOT NULL,
    period        VARCHAR(7),                 -- 'YYYY-MM' para nóminas
    drive_file_id VARCHAR(120),
    mime_type     VARCHAR(80) NOT NULL DEFAULT 'application/pdf',
    content_hash  VARCHAR(64),
    uploaded_by   UUID REFERENCES users(id) ON DELETE SET NULL,   -- NULL = sync automático
    uploaded_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_employee_documents_user_cat ON employee_documents(user_id, category);

CREATE TABLE IF NOT EXISTS drive_sync_runs (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    started_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at  TIMESTAMPTZ,
    status       VARCHAR(20) NOT NULL DEFAULT 'running'
                   CHECK (status IN ('running', 'success', 'partial', 'failed')),
    files_synced INTEGER NOT NULL DEFAULT 0,
    error_detail TEXT
);

-- ----------------------------------------------------------------------------
-- Comunicación: anuncios + buzón anónimo (Fase 5 / Fase 6)
-- ----------------------------------------------------------------------------

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
-- NO hay user_id, ni author, ni FK, ni INET. IMPOSIBLE correlacionar el
-- mensaje con un usuario a nivel de esquema. El endpoint que inserta aquí NO
-- debe registrar IP ni logs con datos de request. reference_code permite
-- seguimiento anónimo; admin_reply/replied_at [014] son la respuesta del
-- admin al emisor SIN vincularla a ninguna identidad.
-- =====================================================================
CREATE TABLE IF NOT EXISTS anonymous_messages (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    reference_code VARCHAR(12) NOT NULL UNIQUE,
    category       VARCHAR(40) CHECK (category IN ('sugerencia', 'consulta', 'incidencia')),
    subject        VARCHAR(200),
    body           TEXT NOT NULL,
    status         VARCHAR(20) NOT NULL DEFAULT 'new'
                     CHECK (status IN ('new', 'read', 'resolved')),
    admin_note     TEXT,                          -- nota interna del admin
    admin_reply    TEXT,                          -- respuesta visible por reference_code
    replied_at     TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_anonymous_messages_status ON anonymous_messages(status);

-- ----------------------------------------------------------------------------
-- Notificaciones + email transaccional (Fase 6)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS notifications (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type       VARCHAR(60) NOT NULL,
    title      VARCHAR(200) NOT NULL,
    body       TEXT,
    data       JSONB NOT NULL DEFAULT '{}',
    read_at    TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications(user_id) WHERE read_at IS NULL;

CREATE TABLE IF NOT EXISTS email_log (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID REFERENCES users(id) ON DELETE SET NULL,
    to_email            VARCHAR(255) NOT NULL,
    template            VARCHAR(80) NOT NULL,
    status              VARCHAR(20) NOT NULL DEFAULT 'queued'
                          CHECK (status IN ('queued', 'sent', 'failed', 'bounced')),
    provider_message_id VARCHAR(160),
    error_detail        TEXT,
    sent_at             TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_email_log_user_id ON email_log(user_id);

-- =============================================================================
-- SEEDS (idempotentes)
-- =============================================================================

INSERT INTO roles (code, name) VALUES
    ('administrador',    'Administrador'),
    ('empleado',         'Empleado'),
    ('externo_invitado', 'Externo-invitado')
ON CONFLICT (code) DO NOTHING;

INSERT INTO entities (code, name) VALUES
    ('hub', 'Amelia Hub'),
    ('lab', 'Amelia Lab'),
    ('ops', 'Amelia Ops')
ON CONFLICT (code) DO NOTHING;

-- Único Administrador (Beatriz Luna, People Manager). Email real de People
-- [007 + 011]. En su primer login con Google, bind_google_login hace la
-- transición 'invited' -> 'active'.
INSERT INTO users (email, full_name, role_id, entity_id, status, is_external)
SELECT
    'people@ameliahub.com',
    'Beatriz Luna',
    (SELECT id FROM roles WHERE code = 'administrador'),
    (SELECT id FROM entities WHERE code = 'hub'),
    'invited',
    FALSE
ON CONFLICT (email) DO NOTHING;

-- Los 6 tipos de ausencia del modal de solicitud [010 + 013], con los colores
-- finales del deck de Fase 3.
INSERT INTO absence_types (code, name, is_paid, affects_balance, default_entitled_days, color) VALUES
    ('vacaciones',      'Vacaciones',      TRUE, TRUE,  23, '#F59F0A'),
    ('baja_medica',     'Baja médica',     TRUE, FALSE, 0,  '#EF4343'),
    ('asuntos_propios', 'Asuntos propios', TRUE, TRUE,  0,  '#3B82F6'),
    ('justificada',     'Justificada',     TRUE, FALSE, 0,  '#6B7280'),
    ('remoto',          'Remoto',          TRUE, FALSE, 0,  '#8B5CF6'),
    ('otros',           'Otros',           TRUE, FALSE, 0,  '#9CA3AF')
ON CONFLICT (code) DO NOTHING;
