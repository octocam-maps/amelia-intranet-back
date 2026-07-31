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
    code       VARCHAR(20) NOT NULL UNIQUE
                 CHECK (code IN ('hub', 'lab', 'ops', 'hincator')),  -- 'hincator' [036]
    name       VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Roles del sistema (administrador / empleado / externo_invitado / socio).
-- socio [024]: igual que un empleado + visión global del calendario de
-- vacaciones (ver + exportar); NO es admin.
CREATE TABLE IF NOT EXISTS roles (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code       VARCHAR(30) NOT NULL UNIQUE
                 CHECK (code IN ('administrador', 'empleado', 'externo_invitado',
                                 'socio',      -- [024]
                                 'becario')),  -- [038] todo salvo control horario
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
    drive_folder_id        VARCHAR(120),    -- [025] carpeta personal en Drive
    vacation_days_override NUMERIC(5,1),    -- [027] NULL = cálculo automático por hire_date
    -- [037] NULL dice "no lo sabemos"; un default diría "es de jornada
    -- completa", que puede ser falso. Independiente de `role_id`: un becario
    -- puede tener cualquier rol y este campo no decide ningún permiso.
    contract_type          TEXT,
    CONSTRAINT ck_users_contract_type CHECK (
        contract_type IS NULL OR contract_type IN ('full_time', 'part_time', 'intern')
    ),
    last_login_at  TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_users_role_id    ON users(role_id);
CREATE INDEX IF NOT EXISTS idx_users_entity_id  ON users(entity_id);
CREATE INDEX IF NOT EXISTS idx_users_manager_id ON users(manager_id);
CREATE INDEX IF NOT EXISTS idx_users_status     ON users(status);

COMMENT ON COLUMN users.vacation_days_override IS
    'Override manual del admin sobre el entitlement anual de vacaciones. '
    'NULL = automático (calculado desde hire_date). No-NULL = el valor fijado '
    'manda sobre el cálculo automático.';

COMMENT ON COLUMN users.contract_type IS
    'full_time | part_time | intern — de la hoja de plantilla. NULL = dato '
    'desconocido, no jornada completa.';

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
    city                    VARCHAR(120),                 -- 022_user_profiles_city.sql: editable en "Mi perfil"
    company_phone           VARCHAR(30),                  -- 026_user_profiles_company_phone.sql: móvil de empresa (opcional, paso 5)
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

-- Traza de cada cambio de rol [039], que antes era destructivo (un UPDATE sobre
-- `users.role_id` sin histórico). `changed_by` es NULLABLE a propósito: el primer
-- admin se sembró directo en `users`, sin invitación, y su autor no se puede
-- saber — NULL dice "no consta" en vez de mentir.
CREATE TABLE IF NOT EXISTS user_role_history (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- NULL = alta inicial (no venía de ningún rol previo).
    from_role_id UUID REFERENCES roles(id) ON DELETE RESTRICT,
    to_role_id   UUID NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    changed_by   UUID REFERENCES users(id) ON DELETE SET NULL,
    changed_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    note         TEXT
);
CREATE INDEX IF NOT EXISTS idx_user_role_history_user
    ON user_role_history(user_id, changed_at DESC);

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
-- [034] MÁXIMO 2 INTENTOS, no uno. El techo vive en
-- `onboarding/domain/policy.py::MAX_QUIZ_ATTEMPTS` y a propósito NO se replica
-- como CHECK aquí; lo que sí garantiza la BD, y solo ella puede, es que no
-- existan dos intentos con el mismo `attempt_number` — el blindaje contra la
-- carrera del doble clic que antes daba `UNIQUE(user_id, step_id)`.
CREATE TABLE IF NOT EXISTS onboarding_quiz_attempts (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    step_id        UUID NOT NULL REFERENCES onboarding_steps(id) ON DELETE CASCADE,
    answers        JSONB NOT NULL,
    score          NUMERIC(5,2) NOT NULL,
    passed         BOOLEAN NOT NULL,
    attempt_number INTEGER NOT NULL DEFAULT 1,
    submitted_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_quiz_attempt_per_number UNIQUE (user_id, step_id, attempt_number),
    CONSTRAINT ck_quiz_attempt_number_positive CHECK (attempt_number >= 1)
);

CREATE TABLE IF NOT EXISTS onboarding_documents (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    kind         VARCHAR(20) NOT NULL CHECK (kind IN ('signature', 'manual')),
    title        VARCHAR(200) NOT NULL,
    version      INTEGER NOT NULL DEFAULT 1,
    content_hash VARCHAR(64) NOT NULL,       -- SHA-256 del documento vigente
    storage_ref  TEXT,
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    -- Orden de lectura dentro de su `kind` [040]. Para kind=manual define la
    -- CASCADA del paso 3: no se confirma un manual sin los de orden menor.
    display_order INTEGER NOT NULL DEFAULT 1,
    -- TRUE = entra en la cascada del paso 3; FALSE = solo biblioteca de
    -- consulta [043]. Separa "está publicado" de "hay que confirmar su lectura".
    requires_acknowledgement BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON COLUMN onboarding_documents.display_order IS
    'Orden de lectura dentro de su `kind`. Para kind=manual define la CASCADA: '
    'no se puede confirmar un manual sin haber confirmado todos los de orden menor.';

COMMENT ON COLUMN onboarding_documents.requires_acknowledgement IS
    'TRUE = hay que confirmar su lectura para completar el paso 3 (entra en la '
    'cascada). FALSE = solo está en la biblioteca de consulta. Los `signature` '
    'no lo usan.';

-- El orden debe ser único entre los que ESTÁN en la cascada [043]: si dos
-- empataran, "el siguiente manual pendiente" sería no determinista. Los de
-- biblioteca no compiten por un puesto de lectura, y por eso quedan fuera.
CREATE UNIQUE INDEX IF NOT EXISTS uq_onboarding_documents_cascade_order
    ON onboarding_documents (kind, display_order)
    WHERE is_active = TRUE AND requires_acknowledgement = TRUE;

-- La firma nativa (`document_signatures`, fecha/hora + IP + hash) se
-- eliminó en `030_drop_document_signatures.sql` (sdd/docs-firmados-upload-
-- drive): el paso 3 ya no firma dentro de la plataforma, sube el PDF ya
-- firmado — ver `employee_documents.category='signed'` y
-- `onboarding_document_uploads` más abajo.

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
    source     VARCHAR(20) NOT NULL DEFAULT 'web'
                   CHECK (source IN ('web', 'mobile', 'manual', 'live')), -- 'manual'/'live' [031]
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
-- Backstop anti-concurrencia (migración 021): una sola pausa abierta por tramo.
CREATE UNIQUE INDEX IF NOT EXISTS uq_time_clock_break_one_open_per_entry
    ON time_clock_breaks (entry_id)
    WHERE break_end IS NULL;

-- Incidencias/comentarios admin sobre un tramo [023]: registro add-only, sin
-- `updated_at` (mismo criterio que `time_clock_breaks`). `author_id` en
-- `ON DELETE SET NULL` para no perder la incidencia si se borra al autor.
CREATE TABLE IF NOT EXISTS time_clock_entry_notes (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entry_id   UUID NOT NULL REFERENCES time_clock_entries(id) ON DELETE CASCADE,
    author_id  UUID REFERENCES users(id) ON DELETE SET NULL,
    body       TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_time_clock_entry_notes_entry_id ON time_clock_entry_notes(entry_id);

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
    -- 'signed' [028]: documento firmado FUERA de la plataforma que el
    -- propio empleado sube en el paso 3 del onboarding (self-upload, ver
    -- onboarding_document_uploads más abajo) — sustituye a la firma nativa.
    category      VARCHAR(20) NOT NULL
                    CHECK (category IN ('payslip', 'contract', 'general', 'other', 'signed')),
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

-- Enlace "este upload de employee_documents satisfizo el paso 3 de
-- onboarding de ESTE usuario" [029] — sin él, `category='signed'` por sí
-- sola no distingue esto de un `signed` suelto que un admin subiera vía
-- `POST /documents` fuera del flujo de onboarding. Referencia tanto a
-- `onboarding_documents` (arriba) como a `employee_documents` (esta
-- sección) — por eso vive aquí y no junto al resto de tablas de Onboarding.
CREATE TABLE IF NOT EXISTS onboarding_document_uploads (
    id                     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id                UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    onboarding_document_id UUID NOT NULL REFERENCES onboarding_documents(id) ON DELETE RESTRICT,
    employee_document_id   UUID NOT NULL REFERENCES employee_documents(id) ON DELETE RESTRICT,
    uploaded_at            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_onboarding_document_upload_user_doc UNIQUE (user_id, onboarding_document_id)
);
CREATE INDEX IF NOT EXISTS idx_onboarding_document_uploads_user_id
    ON onboarding_document_uploads(user_id);

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

-- Plantillas de correo editables por el administrador [041 + 042 + 044].
-- `template_key` es clave natural: coincide 1:1 con el `template` que pasa
-- `IEmailSender.send`, así que no hace falta un JOIN para saber qué plantilla usa
-- un envío. El marco visual del correo (`_shell`) sigue en código; aquí solo
-- viven asunto y cuerpo.
CREATE TABLE IF NOT EXISTS email_templates (
    template_key VARCHAR(80) PRIMARY KEY,
    -- Etiqueta y descripción para la pantalla de administración: sin esto el
    -- admin vería una lista de slugs (`clock_out_missing`) y tendría que
    -- adivinar cuándo se manda cada correo.
    label        VARCHAR(120) NOT NULL,
    description  TEXT NOT NULL,
    subject      TEXT NOT NULL,
    -- TEXTO PLANO, no HTML [044]: la columna se llamaba `body_html` y el nombre
    -- mentía. El HTML lo genera `plain_text_to_html`, que ESCAPA este contenido.
    body         TEXT NOT NULL,
    -- `FALSE` = "usa el texto por defecto del código". Es el botón "Restaurar":
    -- desactivar en vez de borrar conserva lo que el admin había escrito.
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    -- Alcance del aviso, hoy solo lo usa `staff_joined_team` [042]. `'none'`
    -- APAGA el aviso al equipo sin dejar de mandar la bienvenida al recién
    -- llegado, que es distinto de `is_active = FALSE`.
    audience           VARCHAR(20),
    audience_entity_id UUID REFERENCES entities(id) ON DELETE SET NULL,
    updated_by   UUID REFERENCES users(id) ON DELETE SET NULL,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_email_templates_audience CHECK (
        audience IS NULL OR audience IN ('all', 'entity', 'none')
    ),
    -- `entity` sin entidad elegida sería un fan-out a nadie, en silencio.
    CONSTRAINT ck_email_templates_audience_entity CHECK (
        audience <> 'entity' OR audience_entity_id IS NOT NULL
    )
);
CREATE INDEX IF NOT EXISTS idx_email_templates_active
    ON email_templates(template_key) WHERE is_active = TRUE;

COMMENT ON COLUMN email_templates.body IS
    'Cuerpo en TEXTO PLANO escrito por el administrador. Línea en blanco = '
    'párrafo nuevo; `**texto**` = negrita; las URLs y correos se enlazan solos. '
    'El HTML lo genera `plain_text_to_html` y escapa este contenido: aquí NO se '
    'guardan etiquetas.';

-- =============================================================================
-- SEEDS (idempotentes)
-- =============================================================================

INSERT INTO roles (code, name) VALUES
    ('administrador',    'Administrador'),
    ('empleado',         'Empleado'),
    ('externo_invitado', 'Externo-invitado'),
    ('socio',            'Socio'),
    ('becario',          'Becario')
ON CONFLICT (code) DO NOTHING;

INSERT INTO entities (code, name) VALUES
    ('hub',      'Amelia Hub'),
    ('lab',      'Amelia Lab'),
    ('ops',      'Amelia Ops'),
    ('hincator', 'Hincator')
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

-- Catálogo CERRADO de tipos de ausencia [010 + 013 + 019 + 032]. Los 12 de
-- RF-A5, que RECTIFICAN los 6 de RF3.8 (`baja_medica` pasó a llamarse
-- "Enfermedades", y `asuntos_propios` cambió de color): los colores están
-- medidos por contraste y dicromacia en la 032, no elegidos a ojo.
--
-- `default_entitled_days` de `vacaciones` sigue en 23 porque es lo que dejan las
-- migraciones y este archivo REFLEJA su estado, no lo corrige. Pero OJO: ese 23
-- está derogado como saldo real — `absences/domain/vacation_entitlement.py`
-- calcula 20 días/año por semestres completos y es quien manda. Si hay que
-- alinearlo, va en una migración nueva y luego aquí.
INSERT INTO absence_types (
    code, name, is_paid, affects_balance, default_entitled_days, color,
    requires_approval, requires_justification, max_days_per_year
) VALUES
    ('asuntos_propios',        'Asuntos Propios',           TRUE, TRUE,  0.0,  '#C2410C', TRUE, FALSE, NULL),
    ('baja_medica',            'Enfermedades',              TRUE, FALSE, 0.0,  '#EF4343', TRUE, FALSE, NULL),
    ('bloqueado',              'Bloqueado',                 TRUE, FALSE, 0.0,  '#94A3B8', TRUE, FALSE, NULL),
    ('descanso_horas_extra',   'Descanso por horas extra',  TRUE, FALSE, 0.0,  '#78716C', TRUE, FALSE, NULL),
    ('enfermedad_familiar',    'Enfermedad de un familiar', TRUE, FALSE, 0.0,  '#0E7490', TRUE, FALSE, NULL),
    ('fallecimiento_familiar', 'Fallecimiento Familiar',    TRUE, FALSE, 0.0,  '#44403C', TRUE, FALSE, NULL),
    ('justificada',            'Justificada',               TRUE, FALSE, 0.0,  '#6B7280', TRUE, FALSE, NULL),
    ('otros',                  'Otros',                     TRUE, FALSE, 0.0,  '#9CA3AF', TRUE, FALSE, NULL),
    ('paternidad',             'Paternidad',                TRUE, FALSE, 0.0,  '#1E3A8A', TRUE, FALSE, NULL),
    ('permiso_matrimonio',     'Permiso Matrimonio',        TRUE, FALSE, 0.0,  '#F9A8D4', TRUE, FALSE, NULL),
    ('remoto',                 'Remoto',                    TRUE, FALSE, 0.0,  '#8B5CF6', TRUE, FALSE, NULL),
    ('vacaciones',             'Vacaciones',                TRUE, TRUE,  23.0, '#F59F0A', TRUE, FALSE, NULL)
ON CONFLICT (code) DO NOTHING;

-- Los 5 departamentos, para las CUATRO sociedades [036]. El producto cartesiano
-- es deliberado: `departments` no tiene CRUD propio (ver 016), el admin los
-- nombra al dar de alta gente, así que tener el juego completo por entidad es lo
-- que evita duplicados escritos a mano. Sin esto una base nueva arranca con
-- entidades y CERO departamentos, y el alta de plantilla se queda sin opciones.
INSERT INTO departments (entity_id, name)
SELECT e.id, d.name
FROM entities e
CROSS JOIN (VALUES
    ('Administración'),
    ('Comercial'),
    ('Ingeniería'),
    ('Operaciones'),
    ('Producto')
) AS d(name)
ON CONFLICT (entity_id, name) DO NOTHING;

-- Los 5 pasos del onboarding [020], YA EN EL ORDEN VIGENTE de v1.1 [033]:
-- 1 vídeo · 2 cuestionario · 3 manuales · 4 perfil · 5 documentación firmada.
-- El orden vive SOLO en `step_order`; no hay constante equivalente en el código.
-- Sin este seed una base nueva arranca con CERO pasos y el onboarding no existe.
--
-- Shape de `config` por tipo (este seed es el único sitio que lo documenta):
--   video      -> {"url": string, "duration": integer (segundos)}
--   quiz       -> {"questions": [{id, text, options[], correct}], "threshold": 0..1}
--                 `correct` NO viaja al cliente: `_masked_config` lo enmascara.
--   manual / profile / signature -> {} (su material vive en `onboarding_documents`)
INSERT INTO onboarding_steps (step_order, type, title, config) VALUES
    (1, 'video', 'Bienvenida a Amelia',
        '{"url": "/src/assets/videos/hincator.mp4", "duration": 96}'::jsonb),
    (2, 'quiz', 'Cuestionario: El Hincator',
        '{
            "threshold": 0.7,
            "questions": [
                {
                    "id": "q1",
                    "text": "¿Cuántos parámetros críticos captura el Hincator de cada hinca?",
                    "options": ["5", "7", "10", "3"],
                    "correct": "7"
                },
                {
                    "id": "q2",
                    "text": "¿En cuánto tiempo captura el Hincator los parámetros de una hinca?",
                    "options": ["15 segundos", "5 segundos", "1 minuto", "30 segundos"],
                    "correct": "15 segundos"
                },
                {
                    "id": "q3",
                    "text": "¿Cuántas hincas por hora puede inspeccionar?",
                    "options": ["Hasta 50", "Hasta 100", "Hasta 200", "Hasta 25"],
                    "correct": "Hasta 100"
                },
                {
                    "id": "q4",
                    "text": "En zonas remotas, ¿qué garantiza que los datos lleguen del campo a la oficina al instante?",
                    "options": ["Fibra óptica", "Conexión satelital Starlink", "Red 4G", "WiFi"],
                    "correct": "Conexión satelital Starlink"
                }
            ]
        }'::jsonb),
    (3, 'manual',    'Manuales',                      '{}'::jsonb),
    (4, 'profile',   'Completa tu perfil',            '{}'::jsonb),
    (5, 'signature', 'Sube tu documentación firmada', '{}'::jsonb)
ON CONFLICT (step_order) DO NOTHING;

-- Documentos del onboarding [020 + 035 + 040 + 043 + 045]. `onboarding_documents`
-- no tiene UNIQUE natural, así que la idempotencia va con `WHERE NOT EXISTS`
-- sobre `storage_ref` (el de firma, que no tiene, va por `kind` + `version`).
--
-- Los tres manuales se sirven como ASSETS ESTÁTICOS del frontend
-- (`amelia-intranet-web/public/manuales/`), no por `POST /documents`: son
-- material corporativo que publicamos nosotros, así que `DOCUMENTS_MAX_UPLOAD_MB`
-- no les aplica (el del Hincator pesa 12,65 MB). `content_hash` es el SHA-256 del
-- fichero EXACTO que se sirve — lo imprime `amelia-intranet/docs/build-manual-pdf.py
-- <manual> --publish`. Si un PDF se regenera, el hash deja de cuadrar y hay que
-- actualizar su fila: eso es lo que hace verificable la integridad de lo que el
-- trabajador confirma haber leído (RNF2.2).
--
-- Los TRES son obligatorios (`requires_acknowledgement = TRUE`) y su
-- `display_order` es la CASCADA de lectura del paso 3.
INSERT INTO onboarding_documents (kind, title, version, content_hash, storage_ref, display_order, requires_acknowledgement)
SELECT 'manual', 'Manual de uso de ClickUp', 1,
       '03303afd373dfd67c5e1e22e696dcbd57d167a268f01570e8babdd2d3f14e98d',
       '/manuales/manual-clickup-2026-ES.pdf', 1, TRUE
WHERE NOT EXISTS (
    SELECT 1 FROM onboarding_documents
    WHERE kind = 'manual' AND storage_ref = '/manuales/manual-clickup-2026-ES.pdf'
);

INSERT INTO onboarding_documents (kind, title, version, content_hash, storage_ref, display_order, requires_acknowledgement)
SELECT 'manual', 'Manual de usuario Hincator® 2026', 1,
       'b72ce8011190e141b650e3b87a2bd6e15c9e903958035852a545f80473d90731',
       '/manuales/manual-usuario-hincator-2026-ES.pdf', 2, TRUE
WHERE NOT EXISTS (
    SELECT 1 FROM onboarding_documents
    WHERE kind = 'manual' AND storage_ref = '/manuales/manual-usuario-hincator-2026-ES.pdf'
);

INSERT INTO onboarding_documents (kind, title, version, content_hash, storage_ref, display_order, requires_acknowledgement)
SELECT 'manual', 'Manual de uso de la intranet', 1,
       '48b3ba6060556f6449ccc0fa036f2a6c77db50c6fa9d06e4d32779ebba5b9787',
       '/manuales/manual-de-uso-intranet.pdf', 3, TRUE
WHERE NOT EXISTS (
    SELECT 1 FROM onboarding_documents
    WHERE kind = 'manual' AND storage_ref = '/manuales/manual-de-uso-intranet.pdf'
);

-- Documento del paso 5 (la documentación laboral que se descarga, se firma y se
-- vuelve a subir). `content_hash` sigue siendo un PLACEHOLDER: RRHH no ha
-- entregado el PDF definitivo. `storage_ref` a NULL es lo que hace que la UI diga
-- "RRHH todavía no ha publicado este documento" en vez de ofrecer una descarga
-- rota.
INSERT INTO onboarding_documents (kind, title, version, content_hash, storage_ref)
SELECT 'signature', 'Documentación laboral', 1,
       'deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef', NULL
WHERE NOT EXISTS (
    SELECT 1 FROM onboarding_documents WHERE kind = 'signature' AND version = 1
);

-- Las 15 plantillas de correo [041 + 042 + 044], en TEXTO PLANO.
--
-- Las 13 que tienen `{{title}}`/`{{body}}` NO están a medio hacer: son avisos
-- cuyo texto lo genera el código de la notificación in-app, y la plantilla solo
-- decide el envoltorio. Solo `staff_invited` y `staff_joined_team` tienen redacción
-- propia, porque son las dos que no nacen de una notificación.
INSERT INTO email_templates (template_key, label, description, subject, body, audience) VALUES
    ('absence_approved', 'Ausencia aprobada',
     'A la persona solicitante, cuando el administrador aprueba su ausencia.',
     '{{title}}', '{{body}}', NULL),
    ('absence_rejected', 'Ausencia rechazada',
     'A la persona solicitante, cuando el administrador rechaza su ausencia.',
     '{{title}}', '{{body}}', NULL),
    ('absence_requested', 'Ausencia solicitada',
     'Al administrador, cuando alguien solicita una ausencia.',
     '{{title}}', '{{body}}', NULL),
    ('announcement_published', 'Anuncio publicado',
     'A la audiencia del anuncio cuando se publica o se edita.',
     '{{title}}', '{{body}}', NULL),
    ('birthday', 'Cumpleaños',
     'Al equipo, el día del cumpleaños de un compañero.',
     '{{title}}', '{{body}}', NULL),
    ('clock_in_reminder', 'Recordatorio de fichaje',
     'Diario de lunes a viernes, a quien no ha fichado. No se envía a externos ni becarios.',
     '{{title}}', '{{body}}', NULL),
    ('clock_out_missing', 'Jornada sin cerrar',
     'A quien dejó un fichaje abierto el día anterior.',
     '{{title}}', '{{body}}', NULL),
    ('document_pending_signature', 'Documentación pendiente de firmar',
     'A la persona, recordando que le queda subir la documentación firmada.',
     '{{title}}', '{{body}}', NULL),
    ('document_uploaded', 'Documento nuevo',
     'A la persona, cuando se sube un documento a su carpeta.',
     '{{title}}', '{{body}}', NULL),
    ('mailbox_message', 'Mensaje del buzón anónimo',
     'Al administrador, cuando entra un mensaje anónimo. NUNCA incluye datos del remitente.',
     '{{title}}', '{{body}}', NULL),
    ('onboarding_completed', 'Onboarding completado',
     'Al administrador, cuando alguien termina su onboarding.',
     '{{title}}', '{{body}}', NULL),
    ('payslip_available', 'Nómina disponible',
     'A la persona, cuando se publica una nómina en su carpeta.',
     '{{title}}', '{{body}}', NULL),
    ('staff_invited', 'Bienvenida al dar de alta',
     'Se envía a la persona recién dada de alta en la intranet, con el enlace para entrar con su cuenta de Google.',
     'Te damos la bienvenida a la intranet de Amelia',
     'Hola {{full_name}},

RRHH te ha dado de alta en la intranet de Amelia. Accede con tu cuenta de Google corporativa para completar tu onboarding y empezar a gestionar tu jornada, ausencias y documentos.',
     NULL),
    ('staff_joined_team', 'Aviso al equipo de una incorporación',
     'Se envía al equipo cuando se da de alta a alguien nuevo. El alcance de destinatarios se configura aparte.',
     'Nueva incorporación en Amelia: {{full_name}}',
     '{{full_name}} se incorpora a {{entity_name}} como {{job_title}}.

Dadle la bienvenida cuando os cruceis.',
     'all'),
    ('work_anniversary', 'Aniversario laboral',
     'Al equipo, en el aniversario de incorporación de un compañero.',
     '{{title}}', '{{body}}', NULL)
ON CONFLICT (template_key) DO NOTHING;
