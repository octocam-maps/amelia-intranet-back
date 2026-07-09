BEGIN;

-- Fase 3 (realineo visual con docs/deck-fase3/04-modal-solicitar-ausencia.png):
-- el modal de "Nueva solicitud" tiene 6 tarjetas de tipo, pero 010 solo
-- sembró 3 (vacaciones/baja_medica/asuntos_propios) — se completan aquí los
-- 3 que faltaban. `justificada` y `remoto` no descuentan del saldo de
-- vacaciones (affects_balance=FALSE) — misma lógica que baja_medica: son
-- ausencias/situaciones reconocidas, no días de vacaciones consumidos.
-- `otros` queda igual, pendiente de que RRHH defina su semántica exacta.
INSERT INTO absence_types (code, name, is_paid, affects_balance, default_entitled_days, color) VALUES
    ('justificada', 'Justificada', TRUE,  FALSE, 0, '#6B7280'),
    ('remoto',      'Remoto',      TRUE,  FALSE, 0, '#8B5CF6'),
    ('otros',       'Otros',       TRUE,  FALSE, 0, '#9CA3AF')
ON CONFLICT (code) DO NOTHING;

-- Ajuste de color de los 3 tipos sembrados en 010 para que coincidan con los
-- iconos/colores del mockup (vacaciones en ámbar, baja médica en rojo,
-- asuntos propios en azul) — 010 usó una paleta provisional antes de tener
-- el diseño de Fase 3.
UPDATE absence_types SET color = '#F59F0A' WHERE code = 'vacaciones';
UPDATE absence_types SET color = '#EF4343' WHERE code = 'baja_medica';
UPDATE absence_types SET color = '#3B82F6' WHERE code = 'asuntos_propios';

COMMIT;
