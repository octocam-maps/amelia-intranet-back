BEGIN;

-- Corrige el `content_hash` de los dos manuales que añadió la `046`.
--
-- QUÉ CAMBIÓ: la 046 sembró el hash de una versión RE-MAQUETADA de esos dos
-- documentos (traslados a la identidad visual de Amelia, generados desde un HTML
-- fuente con `build-manual-pdf.py`). Decisión del team-lead del 2026-08-06: se
-- publican los PDF ORIGINALES tal como los entregó RRHH, sin re-maquetar. El
-- `storage_ref` no cambia —mismo nombre de fichero en `public/manuales/`—, solo
-- cambia el binario que hay detrás, y con él su SHA-256.
--
-- POR QUÉ UNA MIGRACIÓN NUEVA Y NO EDITAR LA 046: la 046 ya está aplicada, así
-- que sus INSERT no volverían a ejecutarse y el hash viejo se quedaría en la
-- tabla. Editar una migración ya corrida solo arregla las bases de datos que
-- todavía no la habían visto.
--
-- El `content_hash` es registro de integridad: nada lo verifica al servir el
-- fichero, así que un valor obsoleto no rompe la aplicación en ejecución — pero
-- deja de poder responder a "¿es este el documento que se publicó?", que es lo
-- único para lo que existe la columna.
--
-- La `version` NO se sube: el CONTENIDO del documento es el mismo que entregó
-- RRHH (de hecho, es más fielmente el mismo que antes). Lo que cambió es la
-- maquetación con la que se sirve, no lo que la plantilla lee y acepta. Subir la
-- versión invalidaría las confirmaciones de lectura ya registradas en
-- `document_acknowledgements` sin motivo.

UPDATE onboarding_documents
   SET content_hash = '9db4555a9f8b97e8b641c4256f4e2ec7cd308625b2b070d532b700282bcc7f74',
       updated_at = CURRENT_TIMESTAMP
 WHERE kind = 'manual'
   AND storage_ref = '/manuales/protocolo-acoso-amelia-2026.pdf';

UPDATE onboarding_documents
   SET content_hash = 'f9f7f13faa2bcffcd540dce34d6fb80f5c1318f139065846ab6aebae728d0de8',
       updated_at = CURRENT_TIMESTAMP
 WHERE kind = 'manual'
   AND storage_ref = '/manuales/politica-laboral-amelia-2026.pdf';

COMMIT;
