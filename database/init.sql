-- =============================================================================
-- init.sql — Punto de entrada ÚNICO para inicializar el esquema completo de la
-- Amelia Intranet en un entorno nuevo (p. ej. el servidor de hosting).
--
-- Aplica TODAS las migraciones en orden con `\ir` (include relativo a este
-- archivo). Cada migración va envuelta en su propio BEGIN; ... COMMIT;.
--
-- Uso (contra una base de datos VACÍA):
--     psql "$DATABASE_URL" -f database/init.sql
--
-- REGLAS:
--   - Al añadir una migración nueva, agrega su línea `\ir` aquí, EN ORDEN.
--   - NO montes este archivo en /docker-entrypoint-initdb.d junto con
--     ./migrations: Postgres ejecutaría las migraciones dos veces. En Docker
--     local seguimos usando el mount de ./migrations (ver docker-compose.local
--     .yaml); este init.sql es para bring-up manual / servidor.
-- =============================================================================

\set ON_ERROR_STOP on

-- Fase 0-1 · Identidad, acceso y esquema base
\ir migrations/001_core_identity.sql
\ir migrations/002_onboarding.sql
\ir migrations/003_hr_core.sql
\ir migrations/004_documents.sql
\ir migrations/005_admin_comms.sql
\ir migrations/006_notifications.sql
\ir migrations/007_seed_initial_admin.sql
\ir migrations/008_auth_sessions.sql
\ir migrations/009_auth_sessions_family.sql

-- Fase 3 · RRHH core (tipos de ausencia, fichaje)
\ir migrations/010_absence_types_defaults.sql
\ir migrations/011_update_admin_seed_email.sql
\ir migrations/012_time_clock_no_overlap_constraint.sql
\ir migrations/013_absence_types_seed_expansion.sql

-- Fase 6 · Administración (buzón, plantilla, anuncios, festivos, config)
\ir migrations/014_mailbox_reply_status.sql
\ir migrations/015_users_hire_date.sql
\ir migrations/016_departments_unique_name.sql
\ir migrations/017_holidays_updated_at.sql
\ir migrations/018_holidays_source_scope.sql
\ir migrations/019_absence_types_policy_fields.sql
