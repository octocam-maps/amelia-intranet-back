BEGIN;

-- Bootstrap del único Administrador (Beatriz Luna, People Manager).
--
-- `invitations.invited_by` es NOT NULL (siempre hace falta un usuario que
-- invite), así que el primer usuario del sistema no puede darse de alta vía
-- invitación normal — se siembra directamente en `users` con status
-- 'invited'. En su primer login con Google, `bind_google_login` (ver
-- src/features/auth/infrastructure/repositories/user_repository.py) hace la
-- transición 'invited' -> 'active' automáticamente.
--
-- ⚠️ email PLACEHOLDER: debe coincidir EXACTAMENTE con la cuenta real de
-- Google Workspace de Beatriz antes de desplegar. Actualizar aquí o con un
-- UPDATE manual en la BD de producción antes del primer login.
INSERT INTO users (email, full_name, role_id, entity_id, status, is_external)
SELECT
    'beatriz.luna@ameliahub.com',
    'Beatriz Luna',
    (SELECT id FROM roles WHERE code = 'administrador'),
    (SELECT id FROM entities WHERE code = 'hub'),
    'invited',
    FALSE
ON CONFLICT (email) DO NOTHING;

COMMIT;
