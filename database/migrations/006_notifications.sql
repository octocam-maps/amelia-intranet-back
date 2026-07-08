BEGIN;

-- Notificaciones in-app.
CREATE TABLE IF NOT EXISTS notifications (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type       VARCHAR(60) NOT NULL,       -- uno de los ~12 tipos transaccionales
    title      VARCHAR(200) NOT NULL,
    body       TEXT,
    data       JSONB NOT NULL DEFAULT '{}',
    read_at    TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications(user_id) WHERE read_at IS NULL;

-- Registro de email transaccional (SendGrid/Mailgun/SES).
CREATE TABLE IF NOT EXISTS email_log (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID REFERENCES users(id) ON DELETE SET NULL,  -- NULL si no aplica
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

COMMIT;
