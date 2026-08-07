-- ============================================================================
--  PRODUCCIÓN · órdenes y eventos
-- ============================================================================
--
--  Aquí baja a la base lo que antes sólo se cumplía si el código Python se
--  acordaba. La diferencia importa: una regla en el programa vale para quien
--  pasa por el programa; una regla en la base vale **escriba quien escriba**.
--
--  Cuatro cosas que el sistema anterior no podía garantizar y aquí sí:
--
--   1. `terminadas ≤ pintadas ≤ producidas`. Se podía guardar una orden con
--      cero soldadas y cincuenta terminadas, y nada se quejaba.
--   2. El avance se manda **en diferencias**, no en totales. El cliente decía
--      «ahora van 50» y el servidor calculaba el salto contra el valor
--      anterior: dos pestañas a la vez duplicaban el stock. Dos «+5» son +10,
--      que es lo correcto.
--   3. Los eventos no se editan ni se borran. Corregir es meter el evento
--      inverso; un acuse firmado no desaparece del historial.
--   4. El folio sale de una secuencia. El sistema viejo contaba filas, así que
--      dos personas a la vez sacaban el mismo, y tras purgar una orden se
--      reutilizaban folios ya impresos y firmados en un acuse.
-- ============================================================================

create type produccion.estado_orden as enum ('abierta', 'cerrada', 'cancelada');

create table produccion.orden (
  id                     bigint generated always as identity primary key,
  linea                  bigint not null references produccion.linea(id) on delete restrict,

  folio                  text not null unique,
  codigo                 text not null default '',

  cliente                bigint references produccion.cliente(id) on delete restrict,
  obra                   bigint references produccion.obra(id) on delete restrict,
  pieza                  bigint references produccion.pieza_catalogo(id) on delete restrict,

  nombre                 text not null default '',
  descripcion            text not null default '',
  observaciones          text not null default '',

  total_piezas           integer not null default 1 check (total_piezas > 0),
  cantidad_objetivo      integer not null default 1 check (cantidad_objetivo > 0),

  -- Caché. La verdad se obtiene sumando los eventos; estos tres los mantiene
  -- el disparador de abajo y `produccion.recalcular(orden)` los reconstruye.
  cantidad_producida     integer not null default 0 check (cantidad_producida >= 0),
  cantidad_pintada       integer not null default 0 check (cantidad_pintada  >= 0),
  cantidad_terminada     integer not null default 0 check (cantidad_terminada >= 0),

  peso_kg_unitario       numeric(15,6) not null default 0 check (peso_kg_unitario >= 0),

  fecha_compromiso       date,
  prioridad              smallint not null default 3 check (prioridad between 1 and 5),

  etapa_actual           bigint references produccion.etapa(id) on delete restrict,
  estado                 produccion.estado_orden not null default 'abierta',

  cierre_pendiente_en    timestamptz,
  cierre_pendiente_hasta timestamptz,
  cierre_pendiente_por   uuid references plataforma.persona(id),
  cierre_etapa_previa    bigint references produccion.etapa(id) on delete set null,
  cierre_bloqueado_en    timestamptz,

  -- Bloqueo optimista: quien manda una versión vieja recibe un conflicto en
  -- vez de pisar el trabajo de otro sin enterarse.
  version                integer not null default 0,

  -- Lo propio de cada línea. La regla para decidir dónde va un dato: **si se
  -- filtra o se agrega, es columna; si sólo se muestra, es JSON.**
  atributos              jsonb not null default '{}'::jsonb,

  -- Por qué etapas pasa ESTA orden. Vacía significa «las de su línea, todas».
  -- Antes la secuencia era por línea, así que una orden sin pintura se pasaba
  -- por pintura igual y se declaraba sin pintar nada: el sistema registraba una
  -- etapa que no ocurrió, y todo lo que se calcula encima quedaba contaminado.
  ruta                   jsonb not null default '[]'::jsonb,

  creado_por             uuid references plataforma.persona(id),
  creado_en              timestamptz not null default now(),
  ultimo_cambio          timestamptz not null default now(),

  -- ---- LAS INVARIANTES ----
  -- Una pieza no se puede terminar sin pintar, ni pintar sin producir. El
  -- sistema anterior lo dejaba pasar y por eso hay una prueba marcada como
  -- fallo conocido desde hace meses.
  constraint avance_coherente check (
    cantidad_terminada <= cantidad_pintada
    and cantidad_pintada <= cantidad_producida
  ),
  constraint no_se_produce_de_mas check (cantidad_producida <= cantidad_objetivo)
);

create index orden_tablero on produccion.orden (linea, estado, etapa_actual);
create index orden_codigo  on produccion.orden (linea, upper(trim(codigo)));
create index orden_cierre  on produccion.orden (cierre_pendiente_hasta)
  where cierre_pendiente_hasta is not null;

-- ============================================================================
--  El folio, de una secuencia
-- ============================================================================
--
--  Una secuencia por línea, creada al dar de alta la línea. Las secuencias no
--  se deshacen con la transacción: un folio consumido no vuelve, que es
--  justamente lo que se quiere. El anterior sistema contaba filas y reutilizaba
--  folios ya firmados.

create or replace function produccion.crear_secuencia_de_folio()
returns trigger language plpgsql as $$
begin
  execute format('create sequence if not exists produccion.folio_%s start 1', new.codigo);
  return new;
end;
$$;

create trigger linea_crea_su_secuencia
  after insert on produccion.linea
  for each row execute function produccion.crear_secuencia_de_folio();

create or replace function produccion.siguiente_folio(id_linea bigint)
returns text language plpgsql as $$
declare l produccion.linea;
begin
  select * into l from produccion.linea where id = id_linea;
  if not found then
    raise exception 'No existe la línea %', id_linea;
  end if;
  return l.prefijo_folio || '-' ||
         lpad(nextval(format('produccion.folio_%s', l.codigo))::text, 5, '0');
end;
$$;

-- ============================================================================
--  Los eventos: un registro que sólo crece
-- ============================================================================

create type produccion.tipo_evento as enum (
  'creacion', 'cambio_etapa', 'avance', 'cierre_pendiente', 'cierre_firme',
  'reversion_cierre', 'ajuste', 'cancelacion', 'anulacion'
);

create type produccion.contador as enum ('producida', 'pintada', 'terminada');

create table produccion.evento (
  id                 bigint generated always as identity primary key,
  orden              bigint not null references produccion.orden(id) on delete restrict,
  tipo               produccion.tipo_evento not null,

  etapa              bigint references produccion.etapa(id) on delete restrict,
  etapa_anterior     bigint references produccion.etapa(id) on delete restrict,

  -- **Diferencia, no total.** Es lo que hace imposible por construcción que
  -- dos avances simultáneos se pisen: dos «+5» son +10.
  contador           produccion.contador,
  delta              integer not null default 0,
  cantidad_resultante integer,

  motivo             bigint references produccion.motivo(id) on delete restrict,
  comentario         text not null default '',

  actor              uuid references plataforma.persona(id),
  fecha_operacion    date,
  ocurrido_en        timestamptz not null default now(),
  registrado_en      timestamptz not null default now(),

  -- El celular reenvía cuando la red falla. Con esto, el reintento no hace
  -- nada en vez de contar el avance dos veces. Es lo que hace posible la cola
  -- sin conexión de la pantalla del piso.
  clave_idempotencia text unique,

  -- Corregir es meter el evento inverso, no editar el anterior.
  anula_a            bigint references produccion.evento(id) on delete restrict,

  metadata           jsonb not null default '{}'::jsonb,

  constraint avance_lleva_contador check (
    (tipo <> 'avance') or (contador is not null and delta <> 0)
  )
);

create index evento_orden_fecha on produccion.evento (orden, ocurrido_en desc);
create index evento_tipo_fecha  on produccion.evento (tipo, ocurrido_en desc);
create index evento_actor       on produccion.evento (actor, ocurrido_en desc);

-- Ni se editan ni se borran. Sin esto, «registro que sólo crece» es una
-- intención; con esto es una propiedad.
create or replace function produccion.el_historial_no_se_toca()
returns trigger language plpgsql as $$
begin
  raise exception
    'Los eventos no se % : para corregir uno se registra el evento inverso, '
    'con `anula_a`. Un acuse firmado no desaparece del historial.',
    case tg_op when 'UPDATE' then 'modifican' else 'borran' end
    using errcode = 'restrict_violation';
end;
$$;

create trigger evento_inmutable
  before update or delete on produccion.evento
  for each row execute function produccion.el_historial_no_se_toca();

-- ============================================================================
--  Aplicar un evento: los contadores se mantienen solos
-- ============================================================================
--
--  Si los actualizara quien inserta, tarde o temprano alguien se olvidaría y
--  el caché quedaría diciendo una cosa y el registro otra. Aquí no se puede
--  olvidar.

create or replace function produccion.aplicar_evento()
returns trigger language plpgsql as $$
declare permitida boolean;
begin
  if new.tipo = 'avance' then
    update produccion.orden set
      cantidad_producida = cantidad_producida + case when new.contador = 'producida' then new.delta else 0 end,
      cantidad_pintada   = cantidad_pintada   + case when new.contador = 'pintada'   then new.delta else 0 end,
      cantidad_terminada = cantidad_terminada + case when new.contador = 'terminada' then new.delta else 0 end,
      ultimo_cambio = now(),
      version = version + 1
    where id = new.orden;
    -- El `check` de la tabla es quien rechaza si el avance deja los contadores
    -- incoherentes. No hace falta comprobarlo aquí: por eso está allí.

  elsif new.tipo = 'cambio_etapa' then
    -- La transición tiene que estar declarada. Antes esto se comprobaba en el
    -- navegador, así que una petición hecha a mano se lo saltaba entero.
    select exists (
      select 1 from produccion.transicion t
       join produccion.orden o on o.id = new.orden
      where t.linea = o.linea
        and t.hasta = new.etapa
        and (t.desde is not distinct from new.etapa_anterior)
    ) into permitida;

    if not permitida then
      raise exception 'Esa transición no está permitida en esta línea (de % a %)',
        coalesce(new.etapa_anterior::text, 'ninguna'), new.etapa
        using errcode = 'check_violation';
    end if;

    update produccion.orden
       set etapa_actual = new.etapa, ultimo_cambio = now(), version = version + 1
     where id = new.orden;
  end if;

  return new;
end;
$$;

create trigger evento_se_aplica
  after insert on produccion.evento
  for each row execute function produccion.aplicar_evento();

-- Reconstruye los contadores desde el registro. Si el caché y los eventos
-- discrepan, **gana el registro**.
create or replace function produccion.recalcular(id_orden bigint)
returns void language sql as $$
  update produccion.orden o set
    cantidad_producida = coalesce((select sum(delta) from produccion.evento e
                                    where e.orden = o.id and e.contador = 'producida'), 0),
    cantidad_pintada   = coalesce((select sum(delta) from produccion.evento e
                                    where e.orden = o.id and e.contador = 'pintada'), 0),
    cantidad_terminada = coalesce((select sum(delta) from produccion.evento e
                                    where e.orden = o.id and e.contador = 'terminada'), 0)
  where o.id = id_orden;
$$;

-- ============================================================================
--  Quién hace qué
-- ============================================================================

create table produccion.asignacion (
  id           bigint generated always as identity primary key,
  orden        bigint not null references produccion.orden(id) on delete restrict,
  etapa        bigint references produccion.etapa(id) on delete restrict,
  colaborador  bigint references rrhh.colaborador(id) on delete restrict,
  maquina      bigint references produccion.maquina(id) on delete restrict,
  rol          text not null default '',

  -- Qué parte del peso le toca. Sin esto, el indicador de «quién produce
  -- cuánto» le adjudicaba la viga entera a cada uno de los tres que la
  -- tocaron, y la suma daba el triple de lo que salió del taller.
  fraccion_peso numeric(6,4) not null default 1 check (fraccion_peso > 0 and fraccion_peso <= 1),

  vigente      boolean not null default true,
  asignado_por uuid references plataforma.persona(id),
  asignado_en  timestamptz not null default now(),
  retirado_en  timestamptz,

  constraint asignacion_a_alguien_o_algo check (colaborador is not null or maquina is not null)
);

create index asignacion_vigente on produccion.asignacion (orden, etapa) where vigente;
create index asignacion_persona on produccion.asignacion (colaborador) where vigente;

-- ============================================================================
--  Permisos
-- ============================================================================

alter table produccion.orden      enable row level security;
alter table produccion.evento     enable row level security;
alter table produccion.asignacion enable row level security;

grant select on produccion.orden, produccion.evento, produccion.asignacion to authenticated;
grant insert, update on produccion.orden to authenticated;
grant insert on produccion.evento to authenticated;
grant insert, update, delete on produccion.asignacion to authenticated;
grant usage, select on all sequences in schema produccion to authenticated;
grant execute on all functions in schema produccion to authenticated;

create policy orden_lectura on produccion.orden for select
  using (plataforma.tiene_acceso('produccion'));
create policy orden_escritura on produccion.orden for insert
  with check (plataforma.tiene_acceso('produccion'));
create policy orden_cambio on produccion.orden for update
  using (plataforma.tiene_acceso('produccion'))
  with check (plataforma.tiene_acceso('produccion'));

create policy evento_lectura on produccion.evento for select
  using (plataforma.tiene_acceso('produccion'));
create policy evento_alta on produccion.evento for insert
  with check (plataforma.tiene_acceso('produccion'));

create policy asignacion_lectura on produccion.asignacion for select
  using (plataforma.tiene_acceso('produccion'));
create policy asignacion_admin on produccion.asignacion for all
  using (plataforma.tiene_acceso('produccion'))
  with check (plataforma.tiene_acceso('produccion'));
