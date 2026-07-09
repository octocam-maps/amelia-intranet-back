BEGIN;

-- RACE-3 (auditoría QA Fase 3): `find_overlapping_entry` + INSERT en dos
-- queries separadas (application layer) es un check-then-act — dos tramos
-- concurrentes del mismo usuario pueden pasar ambos el check y solaparse en
-- BD. Este constraint es el cinturón de seguridad DETRÁS de ese check: la
-- única fuente de verdad real contra la que Postgres no permite colarse.
--
-- `btree_gist` es necesario para poder combinar columnas de igualdad
-- (`user_id`, `work_date`) con un rango (`tstzrange`) en el mismo EXCLUDE.
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Un tramo abierto (`clock_out IS NULL`) se trata como si llegara hasta
-- 'infinity' a efectos de solape — igual que ya hace `find_overlapping_entry`
-- en la capa de aplicación (COALESCE(clock_out, 'infinity')).
ALTER TABLE time_clock_entries
    ADD CONSTRAINT time_clock_entries_no_overlap
    EXCLUDE USING gist (
        user_id WITH =,
        work_date WITH =,
        tstzrange(clock_in, COALESCE(clock_out, 'infinity'::timestamptz), '[)') WITH &&
    );

COMMIT;
