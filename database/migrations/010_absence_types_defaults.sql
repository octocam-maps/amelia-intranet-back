BEGIN;

-- Fase 3: `absence_types` (003_hr_core.sql) no tenía columna de días
-- entitled por defecto — el cálculo vivía hardcodeado en la app. Se añade
-- aquí para que el prorrateo sea CONFIGURABLE por el admin (Fase 5) sin
-- tocar código: `get_or_create_balance` lee este valor la primera vez que
-- un usuario necesita un saldo para el año en curso.
ALTER TABLE absence_types
    ADD COLUMN IF NOT EXISTS default_entitled_days NUMERIC(5,1) NOT NULL DEFAULT 0;

-- Seed de los 3 tipos mínimos para operar la demo. Valores pendientes de
-- que RRHH responda el cuestionario (ver README backend § "Pendiente RRHH"):
-- - vacaciones: 23 laborables/año es el valor que el propio requerimiento
--   menciona (permisos-roles.md § "Gestión de plantilla").
-- - baja_medica: NO descuenta del saldo de vacaciones (affects_balance=FALSE)
--   — es la práctica habitual en España (IT cubierta por SS/mutua), no un
--   contador de días asignados.
-- - asuntos_propios: sin entitlement por defecto (0 días) hasta que RRHH
--   confirme la política — el admin lo edita en Fase 5 sin migración nueva.
INSERT INTO absence_types (code, name, is_paid, affects_balance, default_entitled_days, color) VALUES
    ('vacaciones',      'Vacaciones',        TRUE,  TRUE,  23, '#00D170'),
    ('baja_medica',     'Baja médica',       TRUE,  FALSE, 0,  '#3C83F6'),
    ('asuntos_propios', 'Asuntos propios',   TRUE,  TRUE,  0,  '#F59F0A')
ON CONFLICT (code) DO NOTHING;

COMMIT;
