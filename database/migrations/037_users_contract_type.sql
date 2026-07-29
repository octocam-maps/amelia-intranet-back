BEGIN;

-- Tipo de contrato en `users` (decisión del team-lead, 2026-07-29): los tres
-- valores que trae la hoja de plantilla, tal cual —Full-Time, Part-Time,
-- Intern—, normalizados a snake_case como el resto de enums del esquema.
--
-- Hasta ahora este dato NO tenía dónde guardarse: la hoja lo traía para las 36
-- personas y el esquema lo tiraba. No es decorativo, condiciona los días de
-- vacaciones.
--
-- NULLable a propósito: los usuarios que ya existen no tienen el dato y ponerles
-- 'full_time' por defecto sería inventárselo. Un `NULL` dice "no lo sabemos",
-- que es la verdad; un default diría "es de jornada completa", que puede ser
-- falso. Quien lo consuma tiene que tratar el nulo.
--
-- La relación con los días de vacaciones NO se codifica aquí. Sigue viviendo en
-- `users.vacation_days_override` y en el catálogo de `absence_types`: derivar
-- días a partir del tipo es una regla de RRHH que puede cambiar sin que cambie
-- el contrato de nadie, y meterla en un CHECK la congelaría.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS contract_type TEXT;

-- `DROP` antes del `ADD`: sin él, un segundo pase de esta migración aborta con
-- "constraint already exists". Este proyecto no tiene runner de migraciones ni
-- tabla de control —se aplican a mano con psql—, así que reejecutar una no es un
-- accidente improbable. Es la misma lección que dejó la 034.
ALTER TABLE users
    DROP CONSTRAINT IF EXISTS ck_users_contract_type;
ALTER TABLE users
    ADD CONSTRAINT ck_users_contract_type
        CHECK (contract_type IS NULL OR contract_type IN ('full_time', 'part_time', 'intern'));

COMMENT ON COLUMN users.contract_type IS
    'full_time | part_time | intern — de la hoja de plantilla. NULL = dato desconocido, no jornada completa.';

COMMIT;
