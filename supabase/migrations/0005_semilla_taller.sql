-- ============================================================================
--  La configuración del taller, tal como es
-- ============================================================================
--
--  Nada de esto está inventado. Sale del sistema que lleva dos años corriendo:
--  las cuatro líneas de `core/constantes.py`, sus opciones de
--  `sembrar_nucleo.py`, la secuencia de etapas de `core/estados.py` y los
--  motivos de paro que el taller ya tiene dados de alta.
--
--  Es idempotente: correrlo dos veces no duplica nada.
-- ============================================================================

-- --------------------------------------------------------------- las líneas
--
-- Lo que de verdad distingue a las cuatro son cinco opciones. Todo lo demás
-- estaba copiado cuatro veces sin aportar ninguna diferencia.

insert into produccion.linea
  (codigo, nombre, prefijo_folio, usa_almacen, usa_acuse, orden_visual) values
  -- Las vigas salen por pedidos y logística de producto terminado, no por el
  -- almacén de piezas.
  ('vigas',    'Estructuras',  'V', false, false, 1),
  ('herreria', 'Herrería',     'H', true,  true,  2),
  ('corta',    'Corta.mx',     'L', true,  true,  3),
  -- Robótica nunca tuvo máquina de estados: las órdenes sólo están abiertas o
  -- cerradas. Es la línea con la que se ensaya cualquier cambio, porque es la
  -- que menos tiene que perder.
  ('robotica', 'Robótica',     'R', false, false, 4)
on conflict (codigo) do nothing;

-- --------------------------------------------------------------- las etapas
--
-- La secuencia por la que pasa una pieza. `Terminado (bloqueo pend.)` va
-- **entre** Terminado y Enviado a propósito: en el sistema viejo quedaba fuera
-- de la lista, y por eso desde ese estado se podía saltar a cualquier otro sin
-- que la comprobación de retroceso dijera nada. Era un fallo de permisos
-- disfrazado de fallo de pantalla.

insert into produccion.etapa (linea, codigo, nombre, orden, es_espera, es_terminal, es_cierre_pendiente)
select l.id, e.codigo, e.nombre, e.orden, e.es_espera, e.es_terminal, e.es_cierre
from produccion.linea l
cross join (values
  ('espera_corte',     'Espera de corte',           1,  true,  false, false),
  ('corte',            'Corte',                     2,  false, false, false),
  ('espera_armado',    'Espera de armado',          3,  true,  false, false),
  ('armado',           'Armado',                    4,  false, false, false),
  ('espera_soldadura', 'Espera de soldadura',       5,  true,  false, false),
  ('soldadura',        'Soldadura',                 6,  false, false, false),
  ('espera_pintura',   'Espera de pintura',         7,  true,  false, false),
  ('pintura',          'Pintura',                   8,  false, false, false),
  ('terminado',        'Terminado',                 9,  false, false, false),
  ('cierre_pendiente', 'Terminado (bloqueo pend.)', 10, false, false, true),
  ('enviado',          'Enviado',                   11, false, true,  false)
) as e(codigo, nombre, orden, es_espera, es_terminal, es_cierre)
where l.codigo in ('vigas', 'herreria', 'corta')
on conflict (linea, codigo) do nothing;

-- Robótica lleva las suyas, que son las que ya usan sus asignaciones.
insert into produccion.etapa (linea, codigo, nombre, orden, es_espera, es_terminal, es_cierre_pendiente)
select l.id, e.codigo, e.nombre, e.orden, e.es_espera, e.es_terminal, e.es_cierre
from produccion.linea l
cross join (values
  ('espera_corte',     'Espera de corte',           1, true,  false, false),
  ('corte',            'Corte',                     2, false, false, false),
  ('espera_soldadura', 'Espera de soldadura',       3, true,  false, false),
  ('soldadura',        'Soldadura',                 4, false, false, false),
  ('cierre_pendiente', 'Terminado (bloqueo pend.)', 5, false, false, true),
  ('enviado',          'Enviado',                   6, false, true,  false)
) as e(codigo, nombre, orden, es_espera, es_terminal, es_cierre)
where l.codigo = 'robotica'
on conflict (linea, codigo) do nothing;

-- ------------------------------------------------------------ los alias
--
-- Cómo se escribió cada etapa a lo largo de los años. Sin esto, «Espera Armado»
-- y «Espera de armado» son dos estados distintos para la base y el mismo para
-- una persona.

insert into produccion.etapa_alias (etapa, alias)
select distinct on (upper(trim(a.alias))) e.id, a.alias
from produccion.etapa e
join (values
  ('espera_corte',     'Espera Corte'),
  ('espera_armado',    'Espera Armado'),
  ('espera_soldadura', 'Espera Soldadura'),
  ('espera_pintura',   'Espera Pintura'),
  ('cierre_pendiente', 'Terminado (bloqueo pendiente)')
) as a(codigo, alias) on a.codigo = e.codigo
order by upper(trim(a.alias)), e.id
on conflict do nothing;

-- ------------------------------------------------------- las transiciones
--
-- Cada etapa lleva a la siguiente, y se puede retroceder a la anterior dando
-- un motivo. **Esto es lo que antes sólo comprobaba el navegador**: una
-- petición hecha a mano se saltaba las reglas enteras.

-- Nacer: la primera etapa de cada línea.
insert into produccion.transicion (linea, desde, hasta)
select l.id, null, e.id
from produccion.linea l
join produccion.etapa e on e.linea = l.id and e.orden = 1
on conflict do nothing;

-- Avanzar.
insert into produccion.transicion (linea, desde, hasta)
select a.linea, a.id, b.id
from produccion.etapa a
join produccion.etapa b on b.linea = a.linea and b.orden = a.orden + 1
on conflict do nothing;

-- Retroceder, siempre con motivo. Nunca se retrocede desde «Enviado»: lo que
-- ya salió del taller no vuelve con un clic.
insert into produccion.transicion (linea, desde, hasta, requiere_motivo, es_retroceso)
select a.linea, a.id, b.id, true, true
from produccion.etapa a
join produccion.etapa b on b.linea = a.linea and b.orden = a.orden - 1
where not a.es_terminal
on conflict do nothing;

-- -------------------------------------------------------------- los motivos
--
-- Los de paro salen de los que el taller ya tiene dados de alta.

insert into produccion.motivo (ambito, codigo, nombre, es_sistema) values
  ('paro', 'falta_material',      'Falta de material',      false),
  ('paro', 'falta_planos',        'Falta de planos',        false),
  ('paro', 'falta_suministros',   'Falta de suministros',   false),
  ('paro', 'mantenimiento',       'Mantenimiento',          false),
  ('paro', 'mantenimiento_plan',  'Mantenimiento planeado', false),
  ('paro', 'cambio_herramienta',  'Cambio de herramienta',  false),
  ('paro', 'energia',             'Energía',                false),
  ('paro', 'espera_calidad',      'Espera de calidad',      false),
  ('paro', 'limpieza',            'Limpieza / orden',       false),
  ('paro', 'logistica_interna',   'Logística interna',      false),

  ('falla', 'falla_electrica',    'Falla eléctrica',        false),
  ('falla', 'falla_mecanica',     'Falla mecánica',         false),

  ('retroceso', 'error_medida',   'Medida equivocada',      false),
  ('retroceso', 'error_material', 'Material equivocado',    false),
  ('retroceso', 'reproceso',      'Hay que rehacerlo',      false),

  -- Retrabajo tenía **dos definiciones distintas en la misma pantalla**: una
  -- buscaba la palabra en un comentario libre y otra una etiqueta. Aquí es una
  -- fila y se puede contar.
  ('retrabajo', 'retrabajo',      'Retrabajo',              true),

  -- Quien detecta que una orden llegó mal y la devuelve **no tiene ningún
  -- problema**: eso es bueno, está revisando.
  ('rechazo', 'no_corresponde',   'No es lo que se pidió',  false),
  ('rechazo', 'mal_cortado',      'Mal cortado',            false),
  ('rechazo', 'incompleto',       'Faltan piezas',          false)
on conflict (ambito, codigo) do nothing;
