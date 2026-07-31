-- ═══════════════════════════════════════════════════════════════════════════
--  ¿EN QUÉ ESTADO QUEDÓ `email_templates` tras cancelar la 044?
--  SOLO LECTURA. Ejecútalo en la BD donde cancelaste.
--
--  Nota: usa `to_jsonb(t)->>'campo'` en vez de nombrar la columna, porque
--  Postgres valida los nombres al PARSEAR: un `SELECT body_html` fallaría al
--  parsear si ya se renombró, y un `SELECT body` si no. El acceso vía jsonb
--  funciona en los dos estados, que es justo lo que hay que averiguar.
-- ═══════════════════════════════════════════════════════════════════════════

\echo ''
\echo '── 1. ¿Se renombró la columna? ──'
SELECT column_name AS columna_actual
FROM information_schema.columns
WHERE table_name = 'email_templates' AND column_name IN ('body', 'body_html');

\echo '── 2. ¿Cuántas plantillas quedan con etiquetas HTML? ──'
SELECT count(*) AS con_etiquetas, count(*) FILTER (WHERE TRUE) AS total_revisadas
FROM email_templates t
WHERE COALESCE(to_jsonb(t)->>'body', to_jsonb(t)->>'body_html') ~ '<[a-zA-Z/][^>]*>';

\echo '── 3. Muestra del contenido (para verlo con tus ojos) ──'
SELECT template_key,
       left(replace(COALESCE(to_jsonb(t)->>'body', to_jsonb(t)->>'body_html'),
                    chr(10), ' / '), 55) AS cuerpo
FROM email_templates t
ORDER BY template_key
LIMIT 5;

\echo '── 4. ¿Hay transacciones abiertas bloqueando la tabla AHORA? ──'
SELECT pid, state, wait_event_type,
       now() - xact_start AS duracion_transaccion,
       left(query, 60) AS query
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
  AND (state = 'idle in transaction' OR query ILIKE '%email_templates%')
ORDER BY xact_start NULLS LAST;
