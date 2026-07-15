BEGIN;

-- Seed de los 5 pasos de onboarding (Fase 2). Idempotente por
-- `ON CONFLICT (step_order) DO NOTHING` — `onboarding_steps.step_order` ya
-- es UNIQUE (002_onboarding.sql).
--
-- Shape de `config` por tipo (documentado aquí porque es el único lugar que
-- lo define; el backend NO valida el shape a nivel de columna, solo en la
-- capa de aplicación al leer/corregir):
--   video      -> {"url": string, "duration": integer (segundos)}
--   quiz       -> {
--                   "threshold": number 0..1  (fracción de aciertos para aprobar),
--                   "questions": [
--                     {"id": string, "text": string, "options": string[], "correct": string}
--                   ]
--                 }
--                 `correct` NUNCA se devuelve al cliente — el `GET /onboarding/me`
--                 lo enmascara (ver `infrastructure/mappers.py::_masked_config`).
--                 Las respuestas del alumno llegan como `{question.id: opción_elegida}`.
--   signature  -> {} (el documento a firmar vive en `onboarding_documents`, no aquí)
--   manual     -> {} (idem)
--   profile    -> {} (borrador — el esquema real del perfil llega con Fase 3)
INSERT INTO onboarding_steps (step_order, type, title, config) VALUES
    (1, 'video', 'Bienvenida a Amelia',
        '{"url": "/src/assets/videos/hincator.mp4", "duration": 96}'::jsonb),
    (2, 'quiz', 'Cuestionario: El Hincator',
        '{
            "threshold": 0.7,
            "questions": [
                {
                    "id": "q1",
                    "text": "¿Cuántos parámetros críticos captura el Hincator de cada hinca?",
                    "options": ["5", "7", "10", "3"],
                    "correct": "7"
                },
                {
                    "id": "q2",
                    "text": "¿En cuánto tiempo captura el Hincator los parámetros de una hinca?",
                    "options": ["15 segundos", "5 segundos", "1 minuto", "30 segundos"],
                    "correct": "15 segundos"
                },
                {
                    "id": "q3",
                    "text": "¿Cuántas hincas por hora puede inspeccionar?",
                    "options": ["Hasta 50", "Hasta 100", "Hasta 200", "Hasta 25"],
                    "correct": "Hasta 100"
                },
                {
                    "id": "q4",
                    "text": "En zonas remotas, ¿qué garantiza que los datos lleguen del campo a la oficina al instante?",
                    "options": ["Fibra óptica", "Conexión satelital Starlink", "Red 4G", "WiFi"],
                    "correct": "Conexión satelital Starlink"
                }
            ]
        }'::jsonb),
    (3, 'signature', 'Firma de documentación laboral', '{}'::jsonb),
    (4, 'manual', 'Manual del empleado', '{}'::jsonb),
    (5, 'profile', 'Completa tu perfil', '{}'::jsonb)
ON CONFLICT (step_order) DO NOTHING;

-- Documentos asociados a los pasos 3 (firma) y 4 (manual). `content_hash`
-- es un PLACEHOLDER hasta que RRHH suba el documento real (Fase 4/5,
-- integración Drive) — 64 chars hex reconocibles como valor de relleno, NO
-- el hash de un PDF real. Reemplazar junto con `storage_ref` cuando exista
-- el archivo definitivo; eso es una migración nueva (nunca se edita esta).
--
-- `onboarding_documents` (002_onboarding.sql) no tiene una UNIQUE natural
-- sobre (kind, version) — solo `id` — así que `ON CONFLICT` no serviría
-- para la idempotencia. Se usa `WHERE NOT EXISTS` en su lugar.
INSERT INTO onboarding_documents (kind, title, version, content_hash, storage_ref)
SELECT 'signature', 'Documentación laboral', 1,
       'deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef', NULL
WHERE NOT EXISTS (
    SELECT 1 FROM onboarding_documents WHERE kind = 'signature' AND version = 1
);

INSERT INTO onboarding_documents (kind, title, version, content_hash, storage_ref)
SELECT 'manual', 'Manual del empleado', 1,
       'cafebabecafebabecafebabecafebabecafebabecafebabecafebabecafebabe', NULL
WHERE NOT EXISTS (
    SELECT 1 FROM onboarding_documents WHERE kind = 'manual' AND version = 1
);

COMMIT;
