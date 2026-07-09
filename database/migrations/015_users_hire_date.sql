BEGIN;

-- Fase 6 (gestión de plantilla): `docs/permisos-roles.md` § "Gestión de
-- plantilla" liga la fecha de inicio de contrato al cálculo de vacaciones,
-- pero 001_core_identity.sql nunca la modeló — `users` solo tenía
-- `created_at` (fecha de creación del registro, no de alta laboral).
-- Aditiva y nullable: los usuarios ya sembrados (admin, Fases 1-5) no
-- tienen este dato todavía.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS hire_date DATE;

COMMIT;
