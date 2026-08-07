-- ============================================================================
--  RRHH — la gente del taller
-- ============================================================================
--
--  Aquí vive la ficha completa de una persona: cuándo nació, cuándo entró,
--  cuánto gana. Producción **no ve esto**: ve una vista con lo justo para
--  repartir trabajo —quién es, si sigue activo y qué sabe hacer—, sin fecha de
--  nacimiento y sin sueldo.
--
--  Esa vista es el aislamiento entre ERPs hecho de verdad. Un `WHERE` se
--  olvida; una vista que no tiene la columna no la puede filtrar mal.
-- ============================================================================

create schema if not exists rrhh;

-- --------------------------------------------------------- departamentos
--
-- Cómo se divide este taller lo sabe el taller. No se siembra ninguno.

create table rrhh.departamento (
  id             bigint generated always as identity primary key,
  nombre         text not null check (length(trim(nombre)) > 0),
  descripcion    text not null default '',
  activo         boolean not null default true,
  creado_en      timestamptz not null default now(),
  actualizado_en timestamptz not null default now()
);

-- Sin columna `nombre_normalizado`: el índice hace el trabajo y no hay un
-- segundo dato que pueda quedarse desincronizado del primero.
create unique index departamento_nombre_unico on rrhh.departamento (upper(trim(nombre)));

-- ---------------------------------------------------------------- puestos
--
-- Lo que hace una persona. Antes eran cuatro cadenas escritas en el código, así
-- que añadir «Pailero» era tocar el programa.
--
-- `rol_de_produccion` es lo que hace que esto no rompa el reparto de órdenes:
-- el sistema reparte por cuatro papeles, y un puesto nuevo dice a cuál se
-- parece. Vacío significa que no entra en producción, que es lo normal en
-- almacén y en la oficina — y es lo que impide que un almacenista salga
-- propuesto para soldar una viga.

create type rrhh.rol_de_produccion as enum ('soldador', 'auxiliar', 'pintor', 'operador');

create table rrhh.puesto (
  id                bigint generated always as identity primary key,
  nombre            text not null check (length(trim(nombre)) > 0),
  departamento      bigint references rrhh.departamento(id) on delete restrict,
  rol_de_produccion rrhh.rol_de_produccion,
  activo            boolean not null default true,
  creado_en         timestamptz not null default now(),
  actualizado_en    timestamptz not null default now()
);

-- El mismo puesto puede existir en dos departamentos: «Auxiliar» de pintura y
-- «Auxiliar» de corte son dos puestos distintos. `nulls not distinct` para que
-- tampoco se repita entre los que no tienen departamento.
create unique index puesto_unico_por_departamento
  on rrhh.puesto (upper(trim(nombre)), coalesce(departamento, -1));

-- ----------------------------------------------------------- colaborador
--
-- La persona que trabaja aquí. **No es lo mismo que una cuenta**: hoy hay
-- dieciocho colaboradores y sólo algunos entran al sistema, y puede haber
-- cuentas que no sean de nadie del taller. Por eso `persona` es opcional.

create table rrhh.colaborador (
  id                bigint generated always as identity primary key,
  nombre            text not null check (length(trim(nombre)) > 0),

  -- La cuenta con la que entra, si tiene. Sin esto, «Mi trabajo» no le puede
  -- enseñar sus órdenes: el sistema sabría que entró alguien, no quién.
  persona           uuid unique references plataforma.persona(id) on delete set null,

  departamento      bigint references rrhh.departamento(id) on delete restrict,
  puesto            bigint references rrhh.puesto(id) on delete restrict,

  sexo              text check (sexo is null or sexo in ('M', 'F', 'X')),
  fecha_nacimiento  date,
  fecha_ingreso     date,
  telefono          text not null default '',

  -- `numeric`, no coma flotante. Es dinero: en binario 0.1 + 0.2 no da 0.3.
  sueldo_mensual    numeric(12,2) not null default 0 check (sueldo_mensual >= 0),

  activo            boolean not null default true,
  creado_en         timestamptz not null default now(),
  actualizado_en    timestamptz not null default now(),

  -- Un dedo de más al teclear el año se ve aquí y no seis meses después en un
  -- informe de edades.
  constraint nacimiento_creible check (
    fecha_nacimiento is null
    or (fecha_nacimiento < current_date and fecha_nacimiento > current_date - interval '100 years')
  ),
  constraint ingreso_creible check (fecha_ingreso is null or fecha_ingreso <= current_date),
  constraint no_entra_antes_de_nacer check (
    fecha_nacimiento is null or fecha_ingreso is null or fecha_ingreso >= fecha_nacimiento
  )
);

create index on rrhh.colaborador (departamento) where activo;
create index on rrhh.colaborador (puesto) where activo;

-- ============================================================================
--  Lo que Producción puede ver de la gente
-- ============================================================================
--
--  Sin sueldo, sin fecha de nacimiento, sin teléfono. Producción necesita saber
--  a quién asignar una orden, no cuánto gana.

create or replace view rrhh.colaborador_publico
with (security_invoker = true) as
select
  c.id,
  c.nombre,
  c.persona,
  c.activo,
  p.rol_de_produccion,
  p.nombre as puesto,
  d.nombre as departamento
from rrhh.colaborador c
left join rrhh.puesto p       on p.id = c.puesto
left join rrhh.departamento d on d.id = c.departamento;

comment on view rrhh.colaborador_publico is
  'Lo que otras áreas pueden ver de una persona. Un WHERE se olvida; una vista '
  'que no tiene la columna no la puede enseñar por descuido.';

-- ============================================================================
--  Permisos
-- ============================================================================

alter table rrhh.departamento enable row level security;
alter table rrhh.puesto       enable row level security;
alter table rrhh.colaborador  enable row level security;

grant usage on schema rrhh to authenticated;
grant select on all tables in schema rrhh to authenticated;
grant insert, update, delete on rrhh.departamento, rrhh.puesto, rrhh.colaborador to authenticated;
grant usage, select on all sequences in schema rrhh to authenticated;

-- Departamentos y puestos: los ve quien entra a RRHH, y también quien entra a
-- Producción, porque los necesita para asignar. No son datos sensibles.
create policy departamento_lectura on rrhh.departamento for select
  using (plataforma.tiene_acceso('rrhh') or plataforma.tiene_acceso('produccion'));
create policy departamento_admin on rrhh.departamento for all
  using (plataforma.administra('rrhh')) with check (plataforma.administra('rrhh'));

create policy puesto_lectura on rrhh.puesto for select
  using (plataforma.tiene_acceso('rrhh') or plataforma.tiene_acceso('produccion'));
create policy puesto_admin on rrhh.puesto for all
  using (plataforma.administra('rrhh')) with check (plataforma.administra('rrhh'));

-- **La ficha completa sólo la ve RRHH.** Producción entra por la vista, que no
-- tiene las columnas del sueldo.
--
-- Y cada quien se ve a sí mismo: que alguien no pueda consultar su propio
-- sueldo sería absurdo.
create policy colaborador_lectura on rrhh.colaborador for select
  using (
    plataforma.tiene_acceso('rrhh')
    or plataforma.tiene_acceso('produccion')
    or persona = auth.uid()
  );

create policy colaborador_admin on rrhh.colaborador for all
  using (plataforma.administra('rrhh')) with check (plataforma.administra('rrhh'));

-- ============================================================================
--  Nadie se borra
-- ============================================================================
--
--  Sus asignaciones, sus firmas y su rendimiento se quedan en el historial. Sin
--  la ficha, todo eso se queda sin dueño y el historial deja de poder
--  explicarse. Se da de baja poniendo `activo = false`.

create or replace function rrhh.no_se_borra_a_nadie()
returns trigger language plpgsql as $$
begin
  raise exception
    'A % no se le borra la ficha: se le da de baja con activo = false. '
    'Su historial de trabajo dejaría de tener dueño.', old.nombre
    using errcode = 'restrict_violation';
end;
$$;

create trigger colaborador_no_se_borra
  before delete on rrhh.colaborador
  for each row execute function rrhh.no_se_borra_a_nadie();
