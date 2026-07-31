BEGIN;

-- Biblioteca de manuales accesible a TODOS los usuarios (petición del
-- 2026-07-31: "hay que agregar un nuevo endpoint que traiga los manuales de uso y
-- que todos los usuarios de la plataforma puedan utilizarlo").
--
-- EL PROBLEMA QUE RESUELVE ESTA COLUMNA: hoy hay tres manuales publicados en
-- `amelia-intranet-web/public/manuales/`, pero solo dos están en
-- `onboarding_documents` — el manual de uso de la INTRANET (el de la página de
-- Ayuda, 14 capítulos) no está en la BD. Para que el endpoint los devuelva todos
-- hay que registrarlo, y ahí aparece el conflicto: cualquier fila con
-- `kind='manual'` entra automáticamente en la cascada del paso 3, así que
-- registrarlo alargaría el onboarding con un manual más que nadie pidió leer.
--
-- Se separan las dos preguntas: "¿está en la biblioteca?" (todas las filas
-- activas) y "¿hay que confirmar su lectura para pasar del paso 3?"
-- (`requires_acknowledgement`). La biblioteca es un superconjunto del paso.
ALTER TABLE onboarding_documents
    ADD COLUMN IF NOT EXISTS requires_acknowledgement BOOLEAN NOT NULL DEFAULT TRUE;

-- DEFAULT TRUE a propósito: las dos filas que ya existen (ClickUp y Hincator) SON
-- del paso 3, y un default `FALSE` las habría sacado de la cascada en silencio,
-- vaciando el paso de onboarding de golpe.
COMMENT ON COLUMN onboarding_documents.requires_acknowledgement IS
    'TRUE = hay que confirmar su lectura para completar el paso 3 (entra en la '
    'cascada). FALSE = solo está en la biblioteca de consulta. Los `signature` '
    'no lo usan.';

-- Manual de uso de la intranet: a la biblioteca, NO al paso 3.
--
-- `content_hash` es el SHA-256 del fichero servido — lo imprime
-- `amelia-intranet/docs/build-manual-pdf.py uso --publish`. Aquí es solo registro
-- de integridad: sin confirmación de lectura no hay nada que "congelar", pero si
-- el PDF se regenera y el hash deja de cuadrar, se detecta igual.
--
-- `display_order = 3`: detrás de los dos del onboarding. El único orden que
-- importa de verdad es el de la cascada, y este documento no está en ella.
INSERT INTO onboarding_documents (
    kind, title, version, content_hash, storage_ref, display_order,
    requires_acknowledgement
)
SELECT 'manual',
       'Manual de uso de la intranet',
       1,
       '48b3ba6060556f6449ccc0fa036f2a6c77db50c6fa9d06e4d32779ebba5b9787',
       '/manuales/manual-de-uso-intranet.pdf',
       3,
       FALSE
WHERE NOT EXISTS (
    SELECT 1 FROM onboarding_documents
    WHERE kind = 'manual' AND storage_ref = '/manuales/manual-de-uso-intranet.pdf'
);

-- El índice único de la cascada solo debe vigilar a los que ESTÁN en la cascada:
-- un documento de biblioteca no compite por un puesto de lectura obligatoria, y
-- con el índice anterior un tercer manual de consulta habría chocado con el orden
-- 3 de un futuro manual obligatorio.
DROP INDEX IF EXISTS uq_onboarding_documents_active_order;
CREATE UNIQUE INDEX IF NOT EXISTS uq_onboarding_documents_cascade_order
    ON onboarding_documents (kind, display_order)
    WHERE is_active = TRUE AND requires_acknowledgement = TRUE;

COMMIT;
