BEGIN;

-- Corrige el `content_hash` de los dos documentos firmables que pasaron a
-- OVERLAY sobre el PDF original de RRHH.
--
-- QUÉ CAMBIÓ: la `046` sembró el hash del texto de una versión GENERADA de estos
-- documentos (dibujada con reportlab, con la identidad visual de Amelia en el
-- consentimiento y una réplica del formulario de Som Prevenció en el CES). El
-- 2026-08-06 el team-lead decidió servirlos TAL CUAL los entregó RRHH: ahora se
-- toma su PDF como plantilla intacta y solo se estampan encima los datos del
-- perfil. Con eso, el hash de la plantilla pasa a ser el SHA-256 del PDF base
-- (`onboarding/infrastructure/document_templates/`).
--
-- Es el mismo caso que la `047` con los dos manuales, y por el mismo motivo: la
-- 046 ya está aplicada, así que sus INSERT no vuelven a ejecutarse y editarla solo
-- serviría para las bases de datos que aún no la hubieran visto.
--
-- `storage_ref` NO cambia: sigue siendo `generated:<code>`. El documento se
-- continúa produciendo al vuelo por usuario (lleva su nombre y su DNI dentro), lo
-- que cambia es de dónde sale la parte fija.
--
-- La `version` NO se sube: es la MISMA redacción de RRHH — de hecho ahora es
-- literalmente su documento, no una interpretación. Subirla invalidaría sin motivo
-- lo ya registrado.
--
-- LOS OTROS DOS (`rgpd-informacion`, `compromiso-confidencialidad`) no se tocan:
-- siguen generados porque de ellos no hay PDF original, solo el `RGPD_Amelia.docx`
-- que además contiene los dos documentos en un fichero. Cuando RRHH entregue el
-- PDF, harán falta su entrada en `_OVERLAY_SPECS` y una migración como esta.

UPDATE onboarding_documents
   SET content_hash = 'f6d90d3c4bb926c4344e731da65c1d043ebefba3522c5ec9b756974b75707862',
       updated_at = CURRENT_TIMESTAMP
 WHERE storage_ref = 'generated:consentimiento-imagenes';

UPDATE onboarding_documents
   SET content_hash = '3b7155f4f6f05fa22d384e3107619ba4bcf21ad1879fa6b21e33f67284b9a618',
       updated_at = CURRENT_TIMESTAMP
 WHERE storage_ref = 'generated:reconocimiento-medico';

COMMIT;
