BEGIN;

-- Incidencias/comentarios que el admin deja sobre un tramo de fichaje
-- (p.ej. "olvidó fichar salida, corregido a mano tras confirmarlo con la
-- persona") — B-2b. Registro de auditoría ADD-ONLY: sin endpoint de edición
-- ni borrado, así que no lleva `updated_at` (mismo criterio que
-- `time_clock_breaks`, que tampoco lo lleva).
--
-- `author_id` usa `ON DELETE SET NULL` (no CASCADE): si la cuenta del admin
-- autor se elimina algún día, la incidencia sigue siendo un registro válido
-- del fichaje — perder al autor no debe borrar la nota (mismo criterio que
-- `absence_requests.reviewed_by`).
CREATE TABLE IF NOT EXISTS time_clock_entry_notes (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entry_id   UUID NOT NULL REFERENCES time_clock_entries(id) ON DELETE CASCADE,
    author_id  UUID REFERENCES users(id) ON DELETE SET NULL,
    body       TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_time_clock_entry_notes_entry_id ON time_clock_entry_notes(entry_id);

COMMIT;
