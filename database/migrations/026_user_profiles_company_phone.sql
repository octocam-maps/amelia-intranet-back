BEGIN;

-- RF §3.5 (paso 5 del onboarding, "Completar perfil"): de los 7 campos
-- obligatorios/opcionales del formulario, 6 ya tenían columna desde
-- 001_core_identity.sql (`users.full_name`, `users.department_id`,
-- `user_profiles.dni_nif`, `birth_date`, `phone` [móvil personal],
-- `address`) — solo faltaba el "móvil de empresa (si aplica)". Aditiva y
-- nullable: es el único campo opcional de los 7.
ALTER TABLE user_profiles
    ADD COLUMN IF NOT EXISTS company_phone VARCHAR(30);

COMMIT;
