BEGIN;

-- Fase 4 v2 (Documentos, Google Drive real): cachea el id de la subcarpeta
-- de Drive del empleado (carpeta nombrada = users.email, bajo
-- DRIVE_ROOT_FOLDER_ID) para no tener que resolverla por nombre en cada
-- subida/descarga — solo la primera vez que se sube un documento o corre el
-- sync. Aditiva y nullable: NULL hasta esa primera resolución (ver
-- `sdd/fase4-nominas-documentos/design`, decisión "Subcarpeta por empleado").
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS drive_folder_id VARCHAR(120);

COMMIT;
