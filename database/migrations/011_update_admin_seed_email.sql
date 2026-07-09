BEGIN;

-- Cambio de la demo (2026-07-09): el email placeholder de 007 se sustituye
-- por el buzón real de People. NO se edita 007 (ya aplicada en main) — el
-- UPDATE funciona tanto si Beatriz ya inició sesión (login empareja primero
-- por `google_sub`, el email solo es fallback) como si todavía no lo hizo.
UPDATE users
SET email = 'people@ameliahub.com',
    updated_at = CURRENT_TIMESTAMP
WHERE email = 'beatriz.luna@ameliahub.com';

COMMIT;
