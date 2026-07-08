BEGIN;

-- Documentos personales del empleado (nóminas, contratos, generales). RGPD: SIEMPRE
-- filtrado por user_id en el backend; nunca se expone otro user_id en la API.
CREATE TABLE IF NOT EXISTS employee_documents (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,   -- dueño
    category      VARCHAR(20) NOT NULL
                    CHECK (category IN ('payslip', 'contract', 'general', 'other')),
    title         VARCHAR(200) NOT NULL,
    period        VARCHAR(7),                 -- 'YYYY-MM' para nóminas
    drive_file_id VARCHAR(120),               -- id en Google Drive
    mime_type     VARCHAR(80) NOT NULL DEFAULT 'application/pdf',
    content_hash  VARCHAR(64),
    uploaded_by   UUID REFERENCES users(id) ON DELETE SET NULL,   -- NULL = sync automático
    uploaded_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_employee_documents_user_cat ON employee_documents(user_id, category);

-- Auditoría del volcado automático desde Drive (Fase 4).
CREATE TABLE IF NOT EXISTS drive_sync_runs (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    started_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at   TIMESTAMPTZ,
    status        VARCHAR(20) NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'success', 'partial', 'failed')),
    files_synced  INTEGER NOT NULL DEFAULT 0,
    error_detail  TEXT
);

COMMIT;
