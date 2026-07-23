BEGIN;

-- LOGIC-2 (pentest ético, severidad ALTA): el alta manual de un tramo
-- (`CreateTimeClockEntryUseCase`) y el fichaje en vivo (`ClockInUseCase`)
-- escribían el mismo `source='web'` histórico — RRHH no podía auditar cuántas
-- horas eran autodeclaradas frente a fichadas en tiempo real. El fix
-- distingue ambos flujos con 'manual'/'live' (ver `TimeClockSource`), así que
-- el CHECK original (solo 'web'/'mobile') debe ampliarse para aceptarlos.
--
-- Los valores 'web'/'mobile' se conservan en el CHECK (no se migran filas
-- viejas, solo se deja de escribirlas en los flujos nuevos) — mismo criterio
-- que `024_socio_role.sql` al ampliar `roles.code`.
ALTER TABLE time_clock_entries DROP CONSTRAINT time_clock_entries_source_check;
ALTER TABLE time_clock_entries ADD CONSTRAINT time_clock_entries_source_check
    CHECK (source IN ('web', 'mobile', 'manual', 'live'));

COMMIT;
