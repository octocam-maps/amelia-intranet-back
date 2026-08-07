BEGIN;

-- Jornadas que cruzan la medianoche (requerimiento v1.2 §M1). Un técnico que
-- sale a las 08:00 y llega al hotel a la 01:30 hoy NO PUEDE registrar su
-- jornada: `CreateTimeClockEntryUseCase` rechaza que la salida caiga en otro
-- día. Se levanta esa restricción para el parte del técnico, y eso obliga a
-- rehacer este constraint.
--
-- POR QUÉ NO BASTA CON CAMBIAR EL CASO DE USO: el EXCLUDE de la migración 012
-- agrupa por `work_date`. Mientras ningún tramo cruzaba el día, esa columna
-- era una forma barata de acotar la comparación. En cuanto un tramo puede ir
-- del día 5 al 6, dos tramos con `work_date` DISTINTO pero horas solapadas
-- dejan de compararse entre sí: Postgres los mete en grupos diferentes y el
-- solape pasa sin que nada lo detecte. El rango `tstzrange` ya lleva la fecha
-- dentro, así que `user_id` + rango es la comparación correcta y completa.
--
-- Este constraint es MÁS ESTRICTO que el anterior y aplica a TODA la
-- plantilla, no solo a los técnicos. Antes de ejecutar esta migración en
-- producción hay que comprobar que no haya datos que ya lo violen — si los
-- hay, el ALTER falla y la transacción entera se revierte:
--
--   SELECT a.user_id, a.id, b.id, a.work_date, b.work_date
--   FROM time_clock_entries a
--   JOIN time_clock_entries b
--     ON a.user_id = b.user_id AND a.id < b.id AND a.work_date <> b.work_date
--    AND tstzrange(a.clock_in, COALESCE(a.clock_out, 'infinity'::timestamptz), '[)')
--     && tstzrange(b.clock_in, COALESCE(b.clock_out, 'infinity'::timestamptz), '[)');
--
-- Un tramo abierto (`clock_out IS NULL`) se sigue tratando como si llegara a
-- 'infinity', igual que en 012 y que `find_overlapping_entry`.
ALTER TABLE time_clock_entries DROP CONSTRAINT time_clock_entries_no_overlap;

ALTER TABLE time_clock_entries
    ADD CONSTRAINT time_clock_entries_no_overlap
    EXCLUDE USING gist (
        user_id WITH =,
        tstzrange(clock_in, COALESCE(clock_out, 'infinity'::timestamptz), '[)') WITH &&
    );

COMMIT;
