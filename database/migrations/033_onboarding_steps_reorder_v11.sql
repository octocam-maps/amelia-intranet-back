BEGIN;

-- Reordenación del flujo de onboarding pedida por RRHH (v1.1, 2026-07-29):
-- la documentación firmada pasa de ser el paso 3 a ser EL ÚLTIMO, y la
-- lectura de manuales sube al 3 para que nadie llegue a las plantillas sin
-- haber leído antes la documentación de referencia.
--
--   ANTES                          DESPUÉS
--   1 video      Bienvenida        1 video      Bienvenida
--   2 quiz       Cuestionario      2 quiz       Cuestionario
--   3 signature  Documentación     3 manual     Manuales
--   4 manual     Manual            4 profile    Perfil
--   5 profile    Perfil            5 signature  Documentación
--
-- El bloqueo secuencial es data-driven (`unlock_next_step` desbloquea el
-- `locked` de menor `step_order` por encima del completado), así que cambiar
-- estos números ES el cambio de flujo — no hay ninguna constante de orden en
-- el código de aplicación.

-- Fase 1: aparcar en órdenes negativos. `onboarding_steps_step_order_key` es
-- una UNIQUE **no diferible**, así que un UPDATE directo a los valores
-- finales choca contra una fila que todavía ocupa el orden destino. Los
-- negativos no colisionan con ningún valor vigente (no hay CHECK sobre
-- `step_order`), así que sirven de zona intermedia libre.
UPDATE onboarding_steps SET step_order = -step_order WHERE step_order > 0;

-- Fase 2: orden definitivo POR TIPO, no por el orden anterior. Un admin pudo
-- haber tocado títulos vía `PATCH /onboarding/admin/steps/{id}`, pero el
-- `type` es inmutable (no hay endpoint que lo cambie) — es el único
-- discriminador fiable. Declarativo: enumera el estado final completo en vez
-- de aplicar deltas, así que reejecutarlo deja el catálogo igual.
--
-- Si algún día existieran DOS pasos del mismo tipo, este UPDATE violaría la
-- UNIQUE y abortaría la transacción entera: falla ruidosamente en vez de
-- dejar el catálogo a medias. Hoy es imposible (no hay endpoint de creación
-- de pasos, solo PATCH sobre los 5 sembrados en 020).
UPDATE onboarding_steps
SET step_order = CASE type
        WHEN 'video'     THEN 1
        WHEN 'quiz'      THEN 2
        WHEN 'manual'    THEN 3
        WHEN 'profile'   THEN 4
        WHEN 'signature' THEN 5
    END,
    updated_at = CURRENT_TIMESTAMP
WHERE type IN ('video', 'quiz', 'manual', 'profile', 'signature');

-- Red de seguridad: si quedó algún paso en negativo es que su `type` no
-- estaba en el CASE de arriba (tipo nuevo añadido sin actualizar esta
-- migración). Abortar es preferible a dejar un catálogo con órdenes
-- negativos, que rompería el bloqueo secuencial de forma silenciosa.
DO $$
DECLARE
    huerfanos INTEGER;
BEGIN
    SELECT count(*) INTO huerfanos FROM onboarding_steps WHERE step_order < 0;
    IF huerfanos > 0 THEN
        RAISE EXCEPTION
            'Quedan % pasos de onboarding sin orden asignado — hay un `type` fuera del CASE de esta migración.',
            huerfanos;
    END IF;
END $$;

-- El título "Manual del empleado" (seed 020) queda corto: el paso pasa a ser
-- la lectura de TODOS los manuales de referencia (RF-A6: manuales del
-- Hincator en ES/EN, además del manual del empleado). Idempotente por el
-- WHERE — no reescribe un título que el admin ya haya personalizado, mismo
-- criterio que la migración 029.
UPDATE onboarding_steps
SET title = 'Manuales', updated_at = CURRENT_TIMESTAMP
WHERE type = 'manual' AND title = 'Manual del empleado';

-- Renormalización del progreso EN CURSO. Sin esto, quien estuviera a mitad
-- del onboarding se queda en un estado inalcanzable: p. ej. alguien con
-- vídeo+cuestionario hechos tenía `signature` en `available` (antiguo orden
-- 3); tras la reordenación `signature` es el 5 y seguiría operable, mientras
-- `manual` (nuevo 3) y `profile` (nuevo 4) quedarían `locked` para siempre
-- porque `unlock_next_step` solo mira hacia ADELANTE desde el paso que se
-- acaba de completar.
--
-- Criterio: los `completed` no se tocan nunca (nadie tiene que repetir un
-- paso ya hecho). Entre los NO completados, el de menor `step_order` NUEVO
-- pasa a operable y el resto a `locked` — que es exactamente la invariante
-- que mantiene `unlock_next_step`. `in_progress` se preserva para no perder
-- el `progress_pct` a medias del vídeo (`available` lo dejaría igual de
-- operable, pero `in_progress` es la verdad de que ya se empezó).
WITH pendientes AS (
    SELECT p.id,
           p.status,
           row_number() OVER (PARTITION BY p.user_id ORDER BY s.step_order) AS posicion
    FROM onboarding_progress p
    JOIN onboarding_steps s ON s.id = p.step_id
    WHERE p.status <> 'completed'
)
UPDATE onboarding_progress p
SET status = CASE
        WHEN pe.posicion = 1 AND pe.status = 'in_progress' THEN 'in_progress'
        WHEN pe.posicion = 1 THEN 'available'
        ELSE 'locked'
    END,
    updated_at = CURRENT_TIMESTAMP
FROM pendientes pe
WHERE p.id = pe.id;

COMMIT;
