BEGIN;

-- Fase 6, ronda 2 (Festivos › importación oficial). Distingue los festivos
-- traídos automáticamente de la API oficial (Nager.Date: nacionales de España
-- + autonómicos de Cataluña) de los añadidos a mano por el admin (los locales
-- de Barcelona —La Mercè, Segona Pasqua— y los cierres de empresa, que ninguna
-- API gratuita cubre de forma fiable).
--
-- `source` gobierna la idempotencia del import: al reimportar un año, las filas
-- 'oficial' se refrescan pero las 'manual' NUNCA se pisan. `scope` es
-- informativo para el badge de la UI (nacional/autonómico/local/empresa).
ALTER TABLE holidays
    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual'
        CHECK (source IN ('oficial', 'manual'));

ALTER TABLE holidays
    ADD COLUMN IF NOT EXISTS scope TEXT
        CHECK (scope IN ('nacional', 'autonomico', 'local', 'empresa'));

COMMIT;
