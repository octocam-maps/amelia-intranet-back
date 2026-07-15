BEGIN;

-- Backstop anti-concurrencia para las pausas de fichaje: impide dos pausas
-- ABIERTAS simultáneas en el mismo tramo. Un doble clic en "Pausa" (o un
-- reintento de red) bajo carrera podía abrir dos filas con break_end NULL —
-- una quedaba huérfana para siempre y corrompía el contador semanal (ese
-- tramo mostraba 0 min trabajados de forma permanente, sin reparación por
-- API). Análogo al EXCLUDE anti-solape de time_clock_entries (migración 012);
-- aquí un índice único parcial es suficiente.
CREATE UNIQUE INDEX IF NOT EXISTS uq_time_clock_break_one_open_per_entry
    ON time_clock_breaks (entry_id)
    WHERE break_end IS NULL;

COMMIT;
