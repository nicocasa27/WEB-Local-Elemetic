-- ============================================================================
--  PLATAFORMA — quién es quién, y a qué ERP puede entrar
-- ============================================================================
--
--  El portal tiene varias áreas dentro: Producción, Recursos Humanos, Ventas.
--  Cada una es un ERP con sus datos en su propio esquema.
--
--  El modelo de acceso es **mixto**, y la distinción importa:
--
--    · La identidad es una. Una persona, una cuenta, una contraseña.
--    · El permiso es de cada ERP. Quien administra Producción decide quién
--      entra a Producción. El portal no puede otorgarlo, y el superadmin
--      tampoco: puede nombrar al administrador de un área, no darse permisos
--      dentro de ella.
--
--  Esa última regla es la que evita que «administrador de la plataforma» sea
--  una llave maestra a la nómina de todo el mundo.
-- ============================================================================

create schema if not exists plataforma;

-- ----------------------------------------------------------------- personas
--
-- Espejo de `auth.users` con lo que la aplicación necesita enseñar. Se apunta
-- a `auth.users` con `on delete restrict` a propósito: borrar una cuenta
-- dejaría sin autor todo lo que esa persona registró, y el historial dejaría
-- de poder explicarse. Una persona se desactiva, no se borra.

create table plataforma.persona (
  id             uuid primary key references auth.users(id) on delete restrict,
  nombre         text not null check (length(trim(nombre)) > 0),
  correo         text not null,
  telefono       text not null default '',
  activo         boolean not null default true,

  -- Ve todas las áreas y nombra al administrador de cada una. **No** puede
  -- darse a sí mismo un rol dentro de un área: eso lo impide la política de
  -- `membresia_rol`, no la buena voluntad.
  es_superadmin  boolean not null default false,

  creado_en      timestamptz not null default now(),
  actualizado_en timestamptz not null default now()
);

comment on table plataforma.persona is
  'Una fila por persona. Espejo de auth.users con los datos que se enseñan.';

-- ------------------------------------------------------------ aplicaciones
--
-- Las áreas del portal. Es una tabla y no una lista en el código porque añadir
-- un área es algo que hace quien administra, no quien programa.

create table plataforma.aplicacion (
  clave       text primary key check (clave ~ '^[a-z][a-z0-9_]*$'),
  nombre      text not null,
  descripcion text not null default '',
  icono       text not null default '',
  ruta        text not null,               -- a dónde lleva el mosaico
  activa      boolean not null default true,
  orden       smallint not null default 0
);

comment on column plataforma.aplicacion.clave is
  'Coincide con el nombre del esquema de PostgreSQL de ese ERP.';

-- --------------------------------------------------------------- membresía
--
-- Quién puede entrar a qué. Sin fila aquí, no se entra: no hay acceso por
-- omisión, ni siquiera para el superadmin.

create table plataforma.membresia (
  persona      uuid not null references plataforma.persona(id) on delete cascade,
  aplicacion   text not null references plataforma.aplicacion(clave) on delete restrict,
  activa       boolean not null default true,

  -- Quién la dio. Sirve para responder «¿y este quién lo metió?», que es la
  -- primera pregunta cuando alguien ve algo que no debería.
  otorgada_por uuid references plataforma.persona(id),
  otorgada_en  timestamptz not null default now(),

  primary key (persona, aplicacion)
);

-- ------------------------------------------------------------------- roles
--
-- Los roles los define **cada ERP**, no la plataforma. Producción tiene
-- «soldadura» y «corte»; Recursos Humanos tendrá los suyos y no se parecen.
-- Meterlos todos en una lista común obligaría a que un área conociera las
-- otras.

create table plataforma.rol_de_app (
  id          bigserial primary key,
  aplicacion  text not null references plataforma.aplicacion(clave) on delete cascade,
  clave       text not null check (clave ~ '^[a-z][a-z0-9_]*$'),
  nombre      text not null,
  descripcion text not null default '',

  -- Quien lo tiene administra ESA aplicación: puede dar y quitar membresías
  -- dentro de ella. No fuera.
  administra  boolean not null default false,

  orden       smallint not null default 0,
  unique (aplicacion, clave)
);

create table plataforma.membresia_rol (
  persona    uuid   not null,
  aplicacion text   not null,
  rol        bigint not null references plataforma.rol_de_app(id) on delete cascade,
  otorgado_en timestamptz not null default now(),

  primary key (persona, aplicacion, rol),
  -- Un rol sólo se puede tener si hay membresía en esa aplicación, y se va
  -- con ella. Sin esto quedarían roles colgando de gente a la que se le
  -- quitó el acceso, que es la clase de permiso que reaparece meses después.
  foreign key (persona, aplicacion)
    references plataforma.membresia(persona, aplicacion) on delete cascade
);

create index on plataforma.membresia (aplicacion) where activa;
create index on plataforma.rol_de_app (aplicacion);

-- ============================================================================
--  Funciones de acceso
-- ============================================================================
--
--  Las usa cada ERP en sus políticas. `security definer` porque tienen que
--  poder leer `plataforma` aunque quien pregunta sólo vea su propio esquema, y
--  `search_path` fijo para que nadie pueda colar una tabla suya con el mismo
--  nombre.

create or replace function plataforma.es_superadmin()
returns boolean
language sql stable security definer set search_path = plataforma, pg_temp
as $$
  select coalesce(
    (select es_superadmin and activo from plataforma.persona where id = auth.uid()),
    false
  );
$$;

create or replace function plataforma.tiene_acceso(app text)
returns boolean
language sql stable security definer set search_path = plataforma, pg_temp
as $$
  select coalesce(
    (select m.activa and p.activo
       from plataforma.membresia m
       join plataforma.persona p on p.id = m.persona
      where m.persona = auth.uid() and m.aplicacion = app),
    false
  );
$$;

comment on function plataforma.tiene_acceso is
  'Si esta persona puede entrar a ese ERP. El superadmin NO entra por aquí: '
  'ver todas las áreas en el portal es una cosa y entrar a sus datos es otra.';

create or replace function plataforma.tiene_rol(app text, rol_clave text)
returns boolean
language sql stable security definer set search_path = plataforma, pg_temp
as $$
  select coalesce(
    (select true
       from plataforma.membresia_rol mr
       join plataforma.rol_de_app r on r.id = mr.rol
       join plataforma.membresia m
            on m.persona = mr.persona and m.aplicacion = mr.aplicacion
      where mr.persona = auth.uid()
        and mr.aplicacion = app
        and r.clave = rol_clave
        and m.activa
      limit 1),
    false
  );
$$;

create or replace function plataforma.administra(app text)
returns boolean
language sql stable security definer set search_path = plataforma, pg_temp
as $$
  select coalesce(
    (select true
       from plataforma.membresia_rol mr
       join plataforma.rol_de_app r on r.id = mr.rol
       join plataforma.membresia m
            on m.persona = mr.persona and m.aplicacion = mr.aplicacion
      where mr.persona = auth.uid()
        and mr.aplicacion = app
        and r.administra
        and m.activa
      limit 1),
    false
  );
$$;

-- ============================================================================
--  Políticas
-- ============================================================================

alter table plataforma.persona       enable row level security;
alter table plataforma.aplicacion    enable row level security;
alter table plataforma.membresia     enable row level security;
alter table plataforma.rol_de_app    enable row level security;
alter table plataforma.membresia_rol enable row level security;

-- Cada quien se ve a sí mismo. El superadmin ve a todos. Y quien administra un
-- área ve a la gente de esa área, porque si no no podría gestionarla.
create policy persona_lectura on plataforma.persona for select
  using (
    id = auth.uid()
    or plataforma.es_superadmin()
    or exists (
      select 1 from plataforma.membresia m
       where m.persona = plataforma.persona.id
         and plataforma.administra(m.aplicacion)
    )
  );

create policy persona_propia on plataforma.persona for update
  using (id = auth.uid()) with check (id = auth.uid());

create policy persona_admin on plataforma.persona for all
  using (plataforma.es_superadmin()) with check (plataforma.es_superadmin());

-- El catálogo de áreas lo lee cualquiera con sesión: es el mosaico del portal.
-- Que exista un área no es secreto; entrar a ella sí.
create policy aplicacion_lectura on plataforma.aplicacion for select
  using (auth.uid() is not null);

create policy aplicacion_admin on plataforma.aplicacion for all
  using (plataforma.es_superadmin()) with check (plataforma.es_superadmin());

-- Cada quien ve sus propias membresías; quien administra un área ve las de esa
-- área.
create policy membresia_lectura on plataforma.membresia for select
  using (
    persona = auth.uid()
    or plataforma.es_superadmin()
    or plataforma.administra(aplicacion)
  );

-- **Aquí está la regla que define «mixto».** Sólo quien administra ESA
-- aplicación puede dar acceso a ella. El superadmin no aparece: puede nombrar
-- administradores, no colarse.
create policy membresia_alta on plataforma.membresia for insert
  with check (plataforma.administra(aplicacion));

create policy membresia_cambio on plataforma.membresia for update
  using (plataforma.administra(aplicacion))
  with check (plataforma.administra(aplicacion));

create policy membresia_baja on plataforma.membresia for delete
  using (plataforma.administra(aplicacion));

create policy rol_lectura on plataforma.rol_de_app for select
  using (auth.uid() is not null);

create policy rol_admin on plataforma.rol_de_app for all
  using (plataforma.administra(aplicacion))
  with check (plataforma.administra(aplicacion));

create policy membresia_rol_lectura on plataforma.membresia_rol for select
  using (
    persona = auth.uid()
    or plataforma.es_superadmin()
    or plataforma.administra(aplicacion)
  );

create policy membresia_rol_admin on plataforma.membresia_rol for all
  using (plataforma.administra(aplicacion))
  with check (plataforma.administra(aplicacion));

-- ============================================================================
--  Permisos de tabla
-- ============================================================================
--
--  En PostgreSQL son dos rejas, no una, y hay que pasar las dos:
--
--    · `GRANT` decide si el rol puede tocar la tabla **en absoluto**.
--    · Las políticas de RLS deciden **qué filas**.
--
--  Sin el `GRANT`, la política ni se evalúa: sale «permission denied for
--  schema» y parece un fallo de la política cuando no lo es. Aquí el `GRANT` es
--  ancho a propósito —lo fino lo hacen las políticas de arriba—, y `anon` no
--  recibe nada: sin sesión no se ve ni qué áreas existen.

grant usage on schema plataforma to authenticated;

grant select on all tables in schema plataforma to authenticated;
grant insert, update, delete on
  plataforma.membresia, plataforma.membresia_rol, plataforma.rol_de_app,
  plataforma.aplicacion
  to authenticated;
grant update on plataforma.persona to authenticated;
grant usage, select on all sequences in schema plataforma to authenticated;
grant execute on all functions in schema plataforma to authenticated;

-- ============================================================================
--  Alta automática: cada cuenta de Supabase crea su ficha
-- ============================================================================
--
--  Sin esto habría que acordarse de crear la fila a mano cada vez, y el día
--  que a alguien se le olvide esa persona entra y no es nadie.
--
--  **La ficha nace sin ninguna membresía**: existir no es tener acceso.

create or replace function plataforma.al_crear_cuenta()
returns trigger
language plpgsql security definer set search_path = plataforma, pg_temp
as $$
begin
  insert into plataforma.persona (id, nombre, correo)
  values (
    new.id,
    coalesce(nullif(trim(new.raw_user_meta_data->>'nombre'), ''), split_part(new.email, '@', 1)),
    new.email
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists al_crear_cuenta on auth.users;
create trigger al_crear_cuenta
  after insert on auth.users
  for each row execute function plataforma.al_crear_cuenta();

-- ---------------------------------------------------------------- semillas

insert into plataforma.aplicacion (clave, nombre, descripcion, icono, ruta, orden) values
  ('produccion', 'Producción', 'Órdenes, avance en el piso, almacén e indicadores.', 'factory', '/produccion', 1),
  ('rrhh',       'Recursos humanos', 'Personal, departamentos, puestos y nómina.',   'users',   '/rrhh',       2),
  ('ventas',     'Ventas',     'Cotizaciones, clientes y órdenes de compra.',        'receipt', '/ventas',     3)
on conflict (clave) do nothing;

-- Los roles de Producción son los trece que ya existían en `core/roles.py`,
-- que dejan de ser una lista en el código y pasan a ser datos.
insert into plataforma.rol_de_app (aplicacion, clave, nombre, descripcion, administra, orden) values
  ('produccion', 'admin_general',           'Administración general',  'Ve y modifica todo, incluidos usuarios y configuración de planta.', true,  1),
  ('produccion', 'ingenieria',              'Ingeniería',              'Como administración general. Para quien planea la obra.',           true,  2),
  ('produccion', 'corte',                   'Corte',                   'Mueve piezas de espera de corte a corte y a espera de armado.',     false, 3),
  ('produccion', 'soldadura',               'Soldadura',               'Armado y soldadura de estructuras.',                               false, 4),
  ('produccion', 'pintura',                 'Pintura',                 'Pintura y terminado.',                                             false, 5),
  ('produccion', 'robotica',                'Robótica',                'Órdenes de la celda robótica.',                                    false, 6),
  ('produccion', 'herreria',                'Herrería',                'Órdenes en serie de herrería.',                                    false, 7),
  ('produccion', 'herreria_supervision',    'Herrería · supervisión',  'Supervisa herrería.',                                              false, 8),
  ('produccion', 'corte_laser',             'Corta.mx',                'Pedidos de corte láser.',                                          false, 9),
  ('produccion', 'corte_laser_supervision', 'Corta.mx · supervisión',  'Supervisa corte láser.',                                           false, 10),
  ('produccion', 'pedidos_ventas',          'Pedidos y logística',     'Pedidos, envíos y expedientes.',                                   false, 11),
  ('produccion', 'almacen',                 'Almacén',                 'Confirma la entrega de material. Aparte de quien produce.',        false, 12),
  ('produccion', 'configuracion',           'Configuración de planta', 'Etapas, transiciones y motivos.',                                  false, 13),
  ('rrhh',       'admin_rrhh',              'Administración de RRHH',  'Alta de personal, sueldos y organigrama.',                          true,  1),
  ('rrhh',       'consulta',                'Consulta',                'Ve el personal sin sueldos.',                                      false, 2),
  ('ventas',     'admin_ventas',            'Administración de ventas','Cotizaciones y clientes.',                                          true,  1)
on conflict (aplicacion, clave) do nothing;
