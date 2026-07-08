BEGIN;

-- Sesiones de refresh token — revocación server-side (aditiva a Fase 1,
-- no estaba en la versión original de docs/fase-0-esquema-datos.md; se
-- añade tras validación del usuario). Cada refresh JWT emitido por
-- /auth/login y /auth/refresh lleva un claim `jti` único que se persiste
-- aquí: sin una fila activa (revoked_at IS NULL) para ese `jti`, el JWT deja
-- de servir aunque su firma y expiración sigan siendo válidas. Esto es lo
-- que permite logout real (no solo borrar la cookie del navegador) y
-- "cerrar sesión en todos los dispositivos".
CREATE TABLE IF NOT EXISTS auth_sessions (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    jti        VARCHAR(64) NOT NULL UNIQUE,
    issued_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    user_agent TEXT,
    ip_address INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_jti ON auth_sessions(jti);
-- Cobertura para "sesiones activas de un usuario" (logout-all, futura vista
-- de dispositivos conectados en "Mi perfil").
CREATE INDEX IF NOT EXISTS idx_auth_sessions_active ON auth_sessions(user_id) WHERE revoked_at IS NULL;

COMMIT;
