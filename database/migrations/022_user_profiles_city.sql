BEGIN;

-- Lote 2 (Mi perfil editable): el trabajador puede editar su teléfono y
-- ciudad desde `/perfil`. `user_profiles.phone` ya existía (poblado en el
-- paso 5 del onboarding, 001_core_identity.sql) pero no había columna de
-- ciudad en ningún lado del esquema — se añade aquí junto al resto de
-- datos de contacto personales (no en `users`, que es identidad/organización,
-- no datos de contacto editables por el propio usuario).
ALTER TABLE user_profiles
    ADD COLUMN IF NOT EXISTS city VARCHAR(120);

COMMIT;
