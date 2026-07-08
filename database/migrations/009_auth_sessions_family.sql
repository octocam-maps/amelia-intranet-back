BEGIN;

-- Patrón OWASP de rotación de refresh tokens: cada cadena de rotaciones
-- sucesivas (login -> refresh -> refresh -> ...) comparte un `family_id`
-- constante. Al detectar el REUSO de un `jti` ya revocado (alguien usa una
-- copia de un refresh token que ya fue rotado — señal de robo), se revoca
-- la FAMILIA completa, no solo ese `jti`, para no dejar vivo ningún
-- descendiente legítimo que el atacante pudiera haber capturado también.
ALTER TABLE auth_sessions
    ADD COLUMN IF NOT EXISTS family_id UUID NOT NULL DEFAULT uuid_generate_v4();

CREATE INDEX IF NOT EXISTS idx_auth_sessions_family_id ON auth_sessions(family_id);

COMMIT;
