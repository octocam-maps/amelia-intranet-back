BEGIN;

-- Fase 6, ronda 2 (Configuración › Tipos de ausencia). El formulario de
-- gestión del admin (deck-fase6/15) configura tres políticas por tipo que
-- `absence_types` (003_hr_core.sql) aún no modelaba:
--   - requires_approval: si la solicitud pasa por la bandeja de aprobación.
--   - requires_justification: si el empleado debe adjuntar justificante.
--   - max_days_per_year: tope anual de días para ese tipo (NULL = sin tope).
ALTER TABLE absence_types
    ADD COLUMN IF NOT EXISTS requires_approval BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE absence_types
    ADD COLUMN IF NOT EXISTS requires_justification BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE absence_types
    ADD COLUMN IF NOT EXISTS max_days_per_year INTEGER
        CHECK (max_days_per_year IS NULL OR max_days_per_year >= 0);

COMMIT;
