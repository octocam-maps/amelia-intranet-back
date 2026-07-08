BEGIN;

-- Catálogo de pasos (configurable por admin, Fase 5). Orden 1..5 con bloqueo secuencial.
CREATE TABLE IF NOT EXISTS onboarding_steps (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    step_order INTEGER NOT NULL UNIQUE,
    type       VARCHAR(20) NOT NULL
                 CHECK (type IN ('video', 'quiz', 'signature', 'manual', 'profile')),
    title      VARCHAR(160) NOT NULL,
    config     JSONB NOT NULL DEFAULT '{}',   -- p.ej. quiz: preguntas/opciones/umbral; video: url/duración
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Progreso por usuario y paso. El backend calcula el desbloqueo: un paso solo pasa a
-- 'available' si el anterior (por step_order) está 'completed'. Escribir la URL no salta el bloqueo.
CREATE TABLE IF NOT EXISTS onboarding_progress (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    step_id      UUID NOT NULL REFERENCES onboarding_steps(id) ON DELETE CASCADE,
    status       VARCHAR(20) NOT NULL DEFAULT 'locked'
                   CHECK (status IN ('locked', 'available', 'in_progress', 'completed')),
    progress_pct INTEGER NOT NULL DEFAULT 0 CHECK (progress_pct BETWEEN 0 AND 100), -- vídeo 100%
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
    CONSTRAINT uq_quiz_attempt_single UNIQUE (user_id, step_id)  -- intento único a nivel BD
);

-- Documentos corporativos (para firmar o para leer/confirmar). Versionados por integridad.
CREATE TABLE IF NOT EXISTS onboarding_documents (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    kind           VARCHAR(20) NOT NULL CHECK (kind IN ('signature', 'manual')),
    title          VARCHAR(200) NOT NULL,
    version        INTEGER NOT NULL DEFAULT 1,
    content_hash   VARCHAR(64) NOT NULL,       -- SHA-256 del documento vigente
    storage_ref    TEXT,                       -- id de fichero en Drive / ruta
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Firma digital trazable (paso 3): fecha/hora + IP + hash del documento firmado.
CREATE TABLE IF NOT EXISTS document_signatures (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id           UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    document_id       UUID NOT NULL REFERENCES onboarding_documents(id) ON DELETE RESTRICT,
    document_version  INTEGER NOT NULL,          -- versión firmada (congelada)
    document_hash     VARCHAR(64) NOT NULL,      -- SHA-256 capturado AL FIRMAR (integridad verificable)
    signature_hash    VARCHAR(128) NOT NULL,     -- hash de la firma (documento + usuario + timestamp)
    signed_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,  -- fecha y hora
    ip_address        INET NOT NULL,             -- IP del firmante
    user_agent        TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_signature_user_doc_version UNIQUE (user_id, document_id, document_version)
);
CREATE INDEX IF NOT EXISTS idx_document_signatures_user_id ON document_signatures(user_id);

-- Confirmación explícita de lectura de manual (paso 4).
CREATE TABLE IF NOT EXISTS document_acknowledgements (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_id     UUID NOT NULL REFERENCES onboarding_documents(id) ON DELETE RESTRICT,
    acknowledged_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address      INET,
    CONSTRAINT uq_ack_user_doc UNIQUE (user_id, document_id)
);

COMMIT;
