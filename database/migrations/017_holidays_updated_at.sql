BEGIN;

-- Fase 6, ronda 2 (Administración › Festivos): `holidays` (003_hr_core.sql)
-- no tenía `updated_at` — hasta ahora el admin no podía editar un festivo ya
-- creado, solo `list_holiday_dates` lo leía (features/absences). El CRUD
-- admin (editar fecha/nombre/ámbito) necesita registrar cuándo se tocó.
ALTER TABLE holidays
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;

COMMIT;
