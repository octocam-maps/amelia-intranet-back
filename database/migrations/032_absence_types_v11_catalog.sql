BEGIN;

-- Ampliación v1.1 RRHH (RF-A5): el catálogo de `absence_types` (003_hr_core.sql,
-- ampliado en 010/013/019) tenía 6 tipos. RRHH pide un catálogo de 10 para
-- cubrir supuestos que hoy caen en el cajón de "Otros" (matrimonio,
-- paternidad, enfermedad de un familiar, descanso por horas extra,
-- bloqueado administrativamente, fallecimiento de un familiar).
--
-- PALETA: verificada empíricamente contra dicromacia (deuteranopía,
-- protanopía, tritanopía) con simulación Machado et al. (2009) + distancia
-- perceptual CIEDE2000 — ver engram
-- `sdd/ampliacion-v11-rrhh/verificacion-paleta-accesibilidad`. La primera
-- paleta propuesta en el design colapsaba dos pares de colores bajo
-- dicromacia rojo-verde (remoto/permiso_matrimonio y remoto/paternidad);
-- esta es la corregida, con CERO pares indistinguibles en las 4 vistas
-- medidas. NO cambiar estos hex sin repetir la medición: por definición 10
-- categorías distinguibles SOLO por color bajo dicromacia es un problema
-- mal planteado (2 ejes útiles para 10 categorías) — por eso el frontend
-- añade un segundo canal (icono/abreviatura) en el chip del calendario
-- (RF-A5.7, WCAG 1.4.1), y el color queda como ayuda, no como único medio.
INSERT INTO absence_types (code, name, is_paid, affects_balance, default_entitled_days, color) VALUES
    ('permiso_matrimonio',     'Permiso Matrimonio',           TRUE, FALSE, 0, '#F9A8D4'),
    ('paternidad',             'Paternidad',                   TRUE, FALSE, 0, '#1E3A8A'),
    ('enfermedad_familiar',    'Enfermedad de un familiar',    TRUE, FALSE, 0, '#0E7490'),
    ('descanso_horas_extra',   'Descanso por horas extra',      TRUE, FALSE, 0, '#78716C'),
    ('bloqueado',              'Bloqueado',                    TRUE, FALSE, 0, '#94A3B8'),
    ('fallecimiento_familiar', 'Fallecimiento Familiar',       TRUE, FALSE, 0, '#44403C')
ON CONFLICT (code) DO NOTHING;

-- Retirada de 'justificada' y 'otros': RRHH decide que estos dos cajones
-- genéricos quedan cubiertos por los tipos nuevos y ya no deben ofrecerse
-- al solicitar una ausencia nueva. Se usa is_active=FALSE, NUNCA DELETE:
-- `absence_requests.absence_type_id` referencia `absence_types` con
-- `ON DELETE RESTRICT` (003_hr_core.sql) — borrar la fila fallaría en cuanto
-- exista una sola solicitud histórica con ese tipo, y aunque no existiera
-- hoy, destruiría la trazabilidad de cualquier solicitud futura importada o
-- de auditoría. is_active=FALSE los saca de los selectores de "nueva
-- solicitud" sin tocar el histórico ni el FK.
UPDATE absence_types SET is_active = FALSE WHERE code IN ('justificada', 'otros');

-- Relabel de 'baja_medica' -> 'Enfermedades': ajuste de nomenclatura pedido
-- por RRHH para que el tipo cubra cualquier enfermedad del propio empleado,
-- no solo baja médica formal. Se conserva el `code` ('baja_medica') a
-- propósito: es la clave estable que usan las solicitudes existentes y
-- cualquier lógica de dominio que compare por code (p.ej. affects_balance);
-- cambiar el code rompería ese histórico sin necesidad, cuando el único
-- cambio pedido es la ETIQUETA visible.
UPDATE absence_types SET name = 'Enfermedades' WHERE code = 'baja_medica';

-- Recolor de 'asuntos_propios': era azul (#3B82F6, fijado en 019), RRHH pide
-- naranja para no solaparse visualmente con "remoto" (violeta) ni con los
-- colores de info de la UI (que ya usan azul). Ver verificación de paleta:
-- naranja quemado #C2410C mantiene buena separación perceptual en las 4
-- vistas simuladas.
UPDATE absence_types SET color = '#C2410C' WHERE code = 'asuntos_propios';

-- Normalización de etiqueta: RRHH escribe "Asuntos Propios" (ambas iniciales
-- en mayúscula) en el listado que fija este catálogo; en BD estaba "Asuntos
-- propios" desde 010. Solo la etiqueta visible, el `code` no se toca.
UPDATE absence_types SET name = 'Asuntos Propios' WHERE code = 'asuntos_propios';

-- GARANTÍA DECLARATIVA del catálogo (imprescindible, no redundante).
--
-- Las 4 sentencias anteriores asumían que los tipos PREEXISTENTES seguían
-- activos, y esa suposición es falsa: `is_active` es mutable en caliente
-- desde Administración › Tipos de ausencia (`UpdateAbsenceTypeUseCase`
-- expone el toggle), así que su valor depende de lo que cada entorno haya
-- tocado por UI. En la BD local, al aplicar esta migración por primera vez,
-- `asuntos_propios` y `baja_medica` estaban en FALSE — alguien los había
-- desactivado probando el CRUD — y el catálogo resultante tenía 8 tipos
-- seleccionables en vez de 10, faltando justamente "Enfermedades".
--
-- Sin este UPDATE la misma migración produce catálogos DISTINTOS en local,
-- staging y producción según su historial de clics. Una migración que define
-- un catálogo cerrado tiene que ser declarativa: enumera el estado final
-- deseado en vez de aplicar deltas sobre un estado que no controla.
UPDATE absence_types SET is_active = TRUE WHERE code IN (
    'vacaciones', 'baja_medica', 'asuntos_propios', 'remoto',
    'permiso_matrimonio', 'paternidad', 'enfermedad_familiar',
    'descanso_horas_extra', 'bloqueado', 'fallecimiento_familiar'
);

COMMIT;

-- ROLLBACK (documentado, no ejecutable automáticamente):
--   BEGIN;
--   UPDATE absence_types SET is_active = TRUE WHERE code IN ('justificada', 'otros');
--   UPDATE absence_types SET name = 'Baja médica' WHERE code = 'baja_medica';
--   UPDATE absence_types SET color = '#3B82F6' WHERE code = 'asuntos_propios';
--   -- El DELETE de los 6 tipos nuevos SOLO es seguro si ninguna solicitud
--   -- los usó todavía (comprobar contra absence_requests.absence_type_id
--   -- antes de borrar; si hay una sola fila, usar is_active=FALSE en su
--   -- lugar, igual que con 'justificada'/'otros'):
--   -- DELETE FROM absence_types WHERE code IN (
--   --   'permiso_matrimonio', 'paternidad', 'enfermedad_familiar',
--   --   'descanso_horas_extra', 'bloqueado', 'fallecimiento_familiar'
--   -- );
--   COMMIT;
