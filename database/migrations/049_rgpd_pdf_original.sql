BEGIN;

-- Últimos dos documentos firmables que pasan a OVERLAY sobre el PDF original.
--
-- RRHH entregó `RGPD_Amelia.pdf` el 2026-08-06 (hasta entonces solo había el
-- `.docx`, y sin PDF base no había nada sobre lo que estampar, así que estos dos
-- se generaban desde cero). Con esto los CUATRO documentos del paso 5 se sirven
-- ya tal cual los entregó RRHH.
--
-- EL PDF SE PARTIÓ EN DOS PLANTILLAS: traía los dos documentos seguidos (art. 13
-- en las páginas 1-2, Compromiso de Confidencialidad en las 3-4), y son documentos
-- con FIRMA INDEPENDIENTE que la persona sube por separado. Servir el fichero
-- entero para ambos obligaría a subir el mismo PDF dos veces para satisfacer dos
-- requisitos distintos, y dejaría en la carpeta de Drive dos copias idénticas con
-- nombres diferentes.
--
-- `content_hash` pasa a ser el SHA-256 del PDF base de cada mitad
-- (`onboarding/infrastructure/document_templates/`), igual que en la 048.
--
-- `storage_ref` NO cambia (`generated:<code>`): el documento se sigue produciendo
-- por usuario, con su nombre, su puesto y su fecha estampados encima.
--
-- `version` NO se sube: es la misma redacción de RRHH — ahora, de hecho,
-- literalmente su documento y no una interpretación nuestra.

UPDATE onboarding_documents
   SET content_hash = 'c29d8b3a1c604b39dc6c3f6bd1e4e267e6b6c42c32f036d9e02b4cd0cefaa861',
       updated_at = CURRENT_TIMESTAMP
 WHERE storage_ref = 'generated:rgpd-informacion';

UPDATE onboarding_documents
   SET content_hash = '7cff43a44020bca3922ff043c6e43c9a250061d8b5320567bbd7ff5403d7b958',
       updated_at = CURRENT_TIMESTAMP
 WHERE storage_ref = 'generated:compromiso-confidencialidad';

COMMIT;
