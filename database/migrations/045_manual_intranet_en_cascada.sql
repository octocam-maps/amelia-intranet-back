BEGIN;

-- El manual de uso de la INTRANET pasa de la biblioteca a la CASCADA del paso 3
-- (petición del 2026-07-31: "agrega el manual de la intranet al onboarding").
--
-- No hay nada que insertar: la fila existe desde `043_manuals_library.sql`, que
-- lo registró con `requires_acknowledgement = FALSE` porque entonces solo se
-- pidió para la biblioteca de consulta (la página de Ayuda). Esa columna es
-- justamente la que separa las dos preguntas, así que añadirlo al onboarding es
-- un UPDATE de un booleano, no un INSERT ni un despliegue.
--
-- Queda TERCERO en la cascada: ClickUp (1, la puerta) -> Hincator (2, el
-- producto) -> intranet (3, la herramienta). `display_order` ya valía 3 desde la
-- 043, así que no compite con nadie por su puesto y
-- `uq_onboarding_documents_cascade_order` —que solo vigila los obligatorios
-- activos— no se altera. Si RRHH prefiere leerlo primero, es otro UPDATE: el
-- orden vive en el dato (decisión de la 040), no en el código.
--
-- Idempotente: reejecutarla no cambia nada una vez el booleano está en TRUE.
UPDATE onboarding_documents
SET requires_acknowledgement = TRUE,
    updated_at = CURRENT_TIMESTAMP
WHERE kind = 'manual'
  AND storage_ref = '/manuales/manual-de-uso-intranet.pdf'
  AND requires_acknowledgement = FALSE;

-- QUIÉN LO VA A LEER Y QUIÉN NO — el efecto que este UPDATE no puede arreglar:
--
-- El paso 3 se cierra cuando están todos los manuales confirmados
-- (`policy.py::are_all_manuals_acknowledged`), pero ese cierre queda PERSISTIDO
-- en `onboarding_progress.status = 'completed'`. Quien ya cerró el paso con dos
-- manuales NO se reabre por añadir un tercero, y no debe reabrirse: hay gente
-- que ya está en el paso 4 o 5, y `unlock_next_step` ya corrió para ellos —
-- devolverlos al 3 los dejaría con tres pasos abiertos a la vez y sería una
-- regresión visible para el trabajador, no una corrección.
--
-- Consecuencia asumida: los que ya terminaron el paso 3 no confirman este manual.
-- Lo tienen igualmente en la biblioteca de Ayuda (`GET /onboarding/manuals`), que
-- es un superconjunto de la cascada. Si RRHH necesita constancia de que la
-- plantilla veterana lo ha leído, eso NO se resuelve reabriendo el paso: se
-- resuelve con un comunicado (Administración > Anuncios) o con un documento de
-- firma, que es el mecanismo que sí deja traza.
--
-- Lo que sí había que arreglar es la UI: con el paso ya `completed`, el frontend
-- listaba el manual nuevo como pendiente y ofrecía "He leído y confirmo", y ese
-- POST responde 422 (`ensure_step_operable`: "Este paso ya está completado").
-- Corregido en `ManualStep.tsx` junto con esta migración.
DO $$
DECLARE
    obligatorios INTEGER;
BEGIN
    SELECT count(*) INTO obligatorios
    FROM onboarding_documents
    WHERE kind = 'manual' AND is_active = TRUE AND requires_acknowledgement = TRUE;

    IF obligatorios <> 3 THEN
        RAISE EXCEPTION
            'La cascada del paso 3 deberia tener 3 manuales obligatorios y tiene %. '
            'Revisa si la 043 se aplico en esta base antes de dar el cambio por hecho.',
            obligatorios;
    END IF;
END $$;

COMMIT;
