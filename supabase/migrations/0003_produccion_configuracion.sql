-- ============================================================================
--  PRODUCCIÓN · configuración — la máquina de estados, como datos
-- ============================================================================
--
--  El sistema anterior tenía la misma máquina de estados **copiada cuatro
--  veces**: vigas, herrería, corta y robótica. Cincuenta y tres modelos para
--  cuatro variantes de lo mismo. Y ya habían divergido: lo que se arreglaba en
--  una línea seguía roto en las otras.
--
--  Aquí las cuatro comparten motor y lo que las distingue son filas de estas
--  tablas. Añadir una etapa de granallado, o una línea nueva, deja de ser un
--  cambio de programa y pasa a ser un `insert`.
-- ============================================================================

create schema if not exists produccion;

-- --------------------------------------------------------- líneas de negocio

create table produccion.linea (
  id                        bigint generated always as identity primary key,
  codigo                    text not null unique check (codigo ~ '^[a-z][a-z0-9_]*$'),
  nombre                    text not null,
  prefijo_folio             text not null check (length(prefijo_folio) between 1 and 6),

  usa_almacen               boolean not null default true,
  usa_acuse                 boolean not null default true,

  -- Minutos que se puede deshacer un cierre. Pasados, lo consolida la tarea
  -- programada, no la próxima persona que abra la pantalla.
  ventana_cierre_minutos    integer not null default 10 check (ventana_cierre_minutos >= 0),
  piezas_minimas_orden_grande integer not null default 2 check (piezas_minimas_orden_grande >= 1),

  activa                    boolean not null default true,
  orden_visual              smallint not null default 0
);

-- ------------------------------------------------------------------ etapas
--
-- El código es estable y en minúsculas; el nombre es lo que se enseña.
--
-- En el sistema viejo el valor guardado **era** la etiqueta, así que «Espera
-- Armado» y «Espera de armado» eran dos estados distintos para la base y el
-- mismo para una persona. Separarlos corta esa clase de fallo de raíz.

create table produccion.etapa (
  id                       bigint generated always as identity primary key,
  linea                    bigint not null references produccion.linea(id) on delete cascade,
  codigo                   text not null check (codigo ~ '^[a-z][a-z0-9_]*$'),
  nombre                   text not null,
  orden                    smallint not null,

  es_espera                boolean not null default false,
  es_terminal              boolean not null default false,
  es_cierre_pendiente      boolean not null default false,
  requiere_asignacion      boolean not null default false,
  requiere_maquina         boolean not null default false,

  color                    text not null default '',

  unique (linea, codigo),
  unique (linea, orden)
);

-- Los nombres que esa etapa tuvo alguna vez. Sirve para leer lo viejo sin que
-- una variante ortográfica se convierta en un estado desconocido.
create table produccion.etapa_alias (
  id     bigint generated always as identity primary key,
  etapa  bigint not null references produccion.etapa(id) on delete cascade,
  alias  text not null
);
create unique index etapa_alias_unico on produccion.etapa_alias (upper(trim(alias)));

-- --------------------------------------------------------- qué se permite
--
-- **Esto es lo que antes vivía sólo en el navegador.** Las tres reglas —no
-- avanzar con la máquina parada, no pasar de la cantidad objetivo, dar motivo
-- al retroceder— se comprobaban en JavaScript, así que una petición hecha a
-- mano se las saltaba enteras.

create table produccion.transicion (
  id                          bigint generated always as identity primary key,
  linea                       bigint not null references produccion.linea(id) on delete cascade,

  -- Nulo significa «desde ninguna parte»: es la etapa en la que nace una orden.
  desde                       bigint references produccion.etapa(id) on delete cascade,
  hasta                       bigint not null references produccion.etapa(id) on delete cascade,

  requiere_motivo             boolean not null default false,
  requiere_rol                text not null default '',
  bloquea_si_maquina_en_paro  boolean not null default false,
  es_retroceso                boolean not null default false
);

create unique index transicion_unica on produccion.transicion (linea, coalesce(desde, -1), hasta);
-- Una sola etapa inicial por línea: si hubiera dos, «dónde nace una orden» no
-- tendría respuesta.
create unique index transicion_inicial_unica on produccion.transicion (linea) where desde is null;

-- ----------------------------------------------------------------- motivos
--
-- Paros, fallas, retrocesos y retrabajos. En el sistema viejo el retrabajo
-- tenía **dos definiciones distintas en la misma pantalla**: una buscaba la
-- palabra en un comentario y otra una etiqueta. Aquí es una fila.

create type produccion.ambito_motivo as enum ('paro', 'falla', 'retroceso', 'retrabajo', 'rechazo');

create table produccion.motivo (
  id         bigint generated always as identity primary key,
  ambito     produccion.ambito_motivo not null,
  codigo     text not null check (codigo ~ '^[a-z][a-z0-9_]*$'),
  nombre     text not null,
  activo     boolean not null default true,
  es_sistema boolean not null default false,
  unique (ambito, codigo)
);

-- ============================================================================
--  Catálogo: a quién se le hace y qué se le hace
-- ============================================================================

create table produccion.cliente (
  id             bigint generated always as identity primary key,
  nombre         text not null check (length(trim(nombre)) > 0),
  rfc            text not null default '',
  correo         text not null default '',
  telefono       text not null default '',
  activo         boolean not null default true,
  creado_en      timestamptz not null default now()
);
create unique index cliente_nombre_unico on produccion.cliente (upper(trim(nombre)));

create table produccion.obra (
  id        bigint generated always as identity primary key,
  cliente   bigint not null references produccion.cliente(id) on delete restrict,
  nombre    text not null check (length(trim(nombre)) > 0),
  activa    boolean not null default true,
  creado_en timestamptz not null default now()
);
create unique index obra_unica_por_cliente on produccion.obra (cliente, upper(trim(nombre)));

create table produccion.pieza_catalogo (
  id             bigint generated always as identity primary key,
  linea          bigint references produccion.linea(id) on delete restrict,
  nombre         text not null check (length(trim(nombre)) > 0),
  descripcion    text not null default '',

  -- Seis decimales, no tres. Aquí se guarda el peso de **una pieza**: a tres
  -- decimales se pierden gramos que reaparecen multiplicados por el número de
  -- piezas, y sobre toneladas eso es dinero. Se detectó comparando una orden
  -- de cuatro piezas de 6.518 kg que volvía a salir como 6.520.
  peso_kg        numeric(15,6) not null default 0 check (peso_kg >= 0),

  -- Rutas en Supabase Storage, no archivos en un disco que nadie respalda.
  plano_pdf      text not null default '',
  plano_dxf      text not null default '',

  activo         boolean not null default true,
  creado_en      timestamptz not null default now()
);
create unique index pieza_nombre_unico on produccion.pieza_catalogo (upper(trim(nombre)));

-- ---------------------------------------------------------------- planta

create table produccion.maquina (
  id        bigint generated always as identity primary key,
  nombre    text not null check (length(trim(nombre)) > 0),
  area      text not null default '',
  activa    boolean not null default true
);
create unique index maquina_nombre_unico on produccion.maquina (upper(trim(nombre)));

create table produccion.equipo (
  id        bigint generated always as identity primary key,
  nombre    text not null check (length(trim(nombre)) > 0),
  area      text not null default '',
  sub_area  text not null default '',
  activo    boolean not null default true
);
create unique index equipo_nombre_unico on produccion.equipo (upper(trim(nombre)));

-- ============================================================================
--  Permisos
-- ============================================================================

alter table produccion.linea           enable row level security;
alter table produccion.etapa           enable row level security;
alter table produccion.etapa_alias     enable row level security;
alter table produccion.transicion      enable row level security;
alter table produccion.motivo          enable row level security;
alter table produccion.cliente         enable row level security;
alter table produccion.obra            enable row level security;
alter table produccion.pieza_catalogo  enable row level security;
alter table produccion.maquina         enable row level security;
alter table produccion.equipo          enable row level security;

grant usage on schema produccion to authenticated;
grant select on all tables in schema produccion to authenticated;
grant insert, update, delete on all tables in schema produccion to authenticated;
grant usage, select on all sequences in schema produccion to authenticated;

-- Todo lo de configuración: lo lee quien entra a Producción, lo cambia quien la
-- administra. Se repite la pareja de políticas por tabla porque PostgreSQL no
-- deja declararlas de golpe.
do $$
declare t text;
begin
  foreach t in array array['linea','etapa','etapa_alias','transicion','motivo',
                           'cliente','obra','pieza_catalogo','maquina','equipo']
  loop
    execute format(
      'create policy %I_lectura on produccion.%I for select using (plataforma.tiene_acceso(''produccion''))',
      t, t);
    execute format(
      'create policy %I_admin on produccion.%I for all
         using (plataforma.administra(''produccion''))
         with check (plataforma.administra(''produccion''))',
      t, t);
  end loop;
end $$;
