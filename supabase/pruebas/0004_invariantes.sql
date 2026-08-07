-- Comprueba, contra la base, las reglas que antes sólo vivían en Python.
-- Cada bloque tiene que fallar (o pasar) por el motivo que dice.
--
--   psql ... -f supabase/pruebas/0004_invariantes.sql
--
-- Se hace todo dentro de una transacción que al final se deshace: no deja nada.

begin;

create temp table resultado (n int, prueba text, esperado text, salio text);

-- Datos mínimos: una línea con dos etapas y su transición.
insert into produccion.linea (codigo, nombre, prefijo_folio) values ('ensayo', 'Ensayo', 'E');
insert into produccion.etapa (linea, codigo, nombre, orden)
select id, 'corte', 'Corte', 1 from produccion.linea where codigo='ensayo';
insert into produccion.etapa (linea, codigo, nombre, orden)
select id, 'pintura', 'Pintura', 2 from produccion.linea where codigo='ensayo';
-- Nace en corte, y de corte se puede pasar a pintura. Nada más.
insert into produccion.transicion (linea, desde, hasta)
select l.id, null, e.id from produccion.linea l join produccion.etapa e on e.linea=l.id
 where l.codigo='ensayo' and e.codigo='corte';
insert into produccion.transicion (linea, desde, hasta)
select l.id, a.id, b.id from produccion.linea l
  join produccion.etapa a on a.linea=l.id and a.codigo='corte'
  join produccion.etapa b on b.linea=l.id and b.codigo='pintura'
 where l.codigo='ensayo';

insert into produccion.orden (linea, folio, cantidad_objetivo, total_piezas, etapa_actual)
select l.id, produccion.siguiente_folio(l.id), 10, 10, e.id
  from produccion.linea l join produccion.etapa e on e.linea=l.id and e.codigo='corte'
 where l.codigo='ensayo';

-- 1 · El folio sale de una secuencia, no de contar filas.
insert into resultado
select 1, 'el folio se genera solo', 'E-00001', folio from produccion.orden;

-- 2 · Un avance suma. Dos avances iguales suman dos veces: son diferencias.
insert into produccion.evento (orden, tipo, contador, delta)
select id, 'avance', 'producida', 4 from produccion.orden;
insert into produccion.evento (orden, tipo, contador, delta)
select id, 'avance', 'producida', 4 from produccion.orden;
insert into resultado
select 2, 'dos avances de +4 suman 8', '8', cantidad_producida::text from produccion.orden;

-- 3 · No se puede terminar lo que no se pintó.  ← el fallo conocido de años
do $$
begin
  insert into produccion.evento (orden, tipo, contador, delta)
  select id, 'avance', 'terminada', 5 from produccion.orden;
  insert into resultado values (3, 'terminar sin pintar', 'RECHAZADO', 'lo aceptó');
exception when check_violation then
  insert into resultado values (3, 'terminar sin pintar', 'RECHAZADO', 'RECHAZADO');
end $$;

-- 4 · No se puede producir más de lo pedido.
do $$
begin
  insert into produccion.evento (orden, tipo, contador, delta)
  select id, 'avance', 'producida', 99 from produccion.orden;
  insert into resultado values (4, 'producir de más', 'RECHAZADO', 'lo aceptó');
exception when check_violation then
  insert into resultado values (4, 'producir de más', 'RECHAZADO', 'RECHAZADO');
end $$;

-- 5 · Una transición que no está declarada se rechaza.
do $$
declare e_pintura bigint;
begin
  select id into e_pintura from produccion.etapa where codigo='pintura';
  -- De «ninguna» a pintura no existe: sólo de corte a pintura.
  insert into produccion.evento (orden, tipo, etapa, etapa_anterior)
  select id, 'cambio_etapa', e_pintura, null from produccion.orden;
  insert into resultado values (5, 'transición no declarada', 'RECHAZADA', 'la aceptó');
exception when check_violation then
  insert into resultado values (5, 'transición no declarada', 'RECHAZADA', 'RECHAZADA');
end $$;

-- 6 · La transición declarada sí pasa, y mueve la orden.
do $$
declare e_corte bigint; e_pintura bigint;
begin
  select id into e_corte   from produccion.etapa where codigo='corte';
  select id into e_pintura from produccion.etapa where codigo='pintura';
  insert into produccion.evento (orden, tipo, etapa, etapa_anterior)
  select id, 'cambio_etapa', e_pintura, e_corte from produccion.orden;
  insert into resultado
  select 6, 'transición declarada', 'pintura', e.codigo
    from produccion.orden o join produccion.etapa e on e.id = o.etapa_actual;
exception when others then
  insert into resultado values (6, 'transición declarada', 'pintura', 'falló: ' || sqlerrm);
end $$;

-- 7 · La clave de idempotencia impide contar dos veces el mismo envío.
do $$
begin
  insert into produccion.evento (orden, tipo, contador, delta, clave_idempotencia)
  select id, 'avance', 'pintada', 1, 'la-misma' from produccion.orden;
  insert into produccion.evento (orden, tipo, contador, delta, clave_idempotencia)
  select id, 'avance', 'pintada', 1, 'la-misma' from produccion.orden;
  insert into resultado values (7, 'reenvío con la misma clave', 'RECHAZADO', 'lo contó dos veces');
exception when unique_violation then
  insert into resultado values (7, 'reenvío con la misma clave', 'RECHAZADO', 'RECHAZADO');
end $$;

-- 8 · El historial no se edita.
do $$
begin
  update produccion.evento set delta = 999 where id = (select min(id) from produccion.evento);
  insert into resultado values (8, 'editar un evento', 'RECHAZADO', 'lo dejó');
exception when restrict_violation then
  insert into resultado values (8, 'editar un evento', 'RECHAZADO', 'RECHAZADO');
end $$;

-- 9 · Ni se borra.
do $$
begin
  delete from produccion.evento where id = (select min(id) from produccion.evento);
  insert into resultado values (9, 'borrar un evento', 'RECHAZADO', 'lo borró');
exception when restrict_violation then
  insert into resultado values (9, 'borrar un evento', 'RECHAZADO', 'RECHAZADO');
end $$;

-- 10 · A nadie se le borra la ficha.
do $$
begin
  insert into rrhh.colaborador (nombre) values ('Prueba');
  delete from rrhh.colaborador where nombre = 'Prueba';
  insert into resultado values (10, 'borrar a una persona', 'RECHAZADO', 'la borró');
exception when restrict_violation then
  insert into resultado values (10, 'borrar a una persona', 'RECHAZADO', 'RECHAZADO');
end $$;

-- 11 · El caché se puede reconstruir desde el registro, y coincide.
do $$
declare antes int; despues int;
begin
  select cantidad_producida into antes from produccion.orden;
  update produccion.orden set cantidad_producida = 0;   -- se estropea a mano
  perform produccion.recalcular((select id from produccion.orden));
  select cantidad_producida into despues from produccion.orden;
  insert into resultado values (11, 'reconstruir desde el registro', antes::text, despues::text);
end $$;

select
  n,
  prueba,
  case when esperado = salio then 'ok' else 'FALLA' end as veredicto,
  esperado, salio
from resultado order by n;

select count(*) filter (where esperado <> salio) || ' fallas de ' || count(*) as resumen
from resultado;

rollback;
