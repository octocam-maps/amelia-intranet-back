BEGIN;

-- Gemelo de `users.drive_folder_id` [025], que faltaba desde el principio.
--
-- Sin esta columna, el id de la carpeta de cada sociedad se resolvía
-- preguntando a Drive por nombre en CADA persona, y se cacheaba en memoria del
-- proveedor. Ese caché tapaba el coste pero no el problema de fondo: dos
-- peticiones simultáneas tienen dos cachés, las dos preguntan si existe
-- «Amelia Hub», las dos reciben que no, y las dos la crean. Drive no impone
-- unicidad por nombre, así que nadie ve un error — media plantilla acaba
-- colgando de una carpeta y media de la otra, y no se detecta hasta que
-- alguien echa en falta una nómina.
ALTER TABLE entities
    ADD COLUMN IF NOT EXISTS drive_folder_id VARCHAR(120);

-- Bajo QUÉ sociedad se creó la carpeta del empleado.
--
-- Permite detectar en SQL —sin preguntar a Drive— a quién hay que recolocar
-- porque cambió de sociedad. Hasta ahora eso era invisible: el provisioning
-- corta en cuanto ve un `drive_folder_id` cacheado, así que corregir el
-- `entity_id` de alguien dejaba su carpeta bajo la sociedad antigua para
-- siempre, sin error y sin aviso.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS drive_folder_entity_id UUID REFERENCES entities(id);

-- Backfill: a quien ya tiene carpeta se le asume colocado bajo su sociedad
-- actual, que es lo que hicieron los volcados existentes. Es una suposición
-- OPTIMISTA a propósito: si falla en algún caso, el provisioning verifica el
-- padre real en Drive antes de mover nada, así que lo peor que puede pasar es
-- una comprobación de más.
--
-- Lo contrario —dejarlo a NULL— marcaría a TODA la plantilla como pendiente de
-- recolocación y dispararía una verificación contra Drive por persona.
UPDATE users
   SET drive_folder_entity_id = entity_id
 WHERE drive_folder_id IS NOT NULL
   AND drive_folder_entity_id IS NULL;

COMMIT;
