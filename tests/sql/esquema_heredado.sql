-- Esquema de las tablas heredadas `vigas` y `production_log`.
--
-- produccion.Viga y produccion.ProductionLog están declarados con
-- managed = False, así que Django no crea estas tablas: ni en la base de
-- pruebas ni en ninguna otra. Sin este archivo, cualquier test que toque
-- vigas falla con "relation does not exist".
--
-- Además de servir a los tests, este archivo es la única documentación que
-- existe del esquema heredado. Antes no estaba escrito en ningún sitio: sólo
-- vivía dentro de la base de producción.
--
-- Se obtuvo con:
--   pg_dump --schema-only --no-owner --no-acl -t public.vigas -t public.production_log
-- y se limpiaron los metacomandos de psql (\restrict) y las opciones propias
-- de PostgreSQL 18, que un cursor de Django no sabe ejecutar.
--
-- Si el esquema cambia en producción, hay que regenerarlo.

CREATE TABLE IF NOT EXISTS public.vigas (
    internal_id integer NOT NULL,
    codigo_viga text NOT NULL,
    pieza_no integer NOT NULL,
    total_piezas integer NOT NULL,
    proyecto text NOT NULL,
    descripcion text NOT NULL,
    fecha_compromiso date NOT NULL,
    estado text NOT NULL,
    observaciones text,
    prioridad integer DEFAULT 3,
    peso_kg numeric(12,2) DEFAULT 0,
    fecha_creacion timestamp without time zone NOT NULL,
    ultimo_cambio timestamp without time zone NOT NULL
);

CREATE SEQUENCE IF NOT EXISTS public.vigas_internal_id_seq
    AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.vigas_internal_id_seq OWNED BY public.vigas.internal_id;
ALTER TABLE ONLY public.vigas
    ALTER COLUMN internal_id SET DEFAULT nextval('public.vigas_internal_id_seq'::regclass);

CREATE TABLE IF NOT EXISTS public.production_log (
    id integer NOT NULL,
    viga_internal_id integer NOT NULL,
    fecha_operacion date NOT NULL,
    estado_anterior text,
    estado_nuevo text NOT NULL,
    comentario text,
    "timestamp" timestamp without time zone NOT NULL,
    usuario text
);

CREATE SEQUENCE IF NOT EXISTS public.production_log_id_seq
    AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.production_log_id_seq OWNED BY public.production_log.id;
ALTER TABLE ONLY public.production_log
    ALTER COLUMN id SET DEFAULT nextval('public.production_log_id_seq'::regclass);

-- Claves primarias y foránea. Nótese que production_log borra en cascada al
-- borrar la viga: es lo que hace que el Decote de vigas destruya también su
-- historial completo.
ALTER TABLE ONLY public.vigas
    ADD CONSTRAINT vigas_pkey PRIMARY KEY (internal_id);
ALTER TABLE ONLY public.production_log
    ADD CONSTRAINT production_log_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.production_log
    ADD CONSTRAINT production_log_viga_internal_id_fkey
    FOREIGN KEY (viga_internal_id) REFERENCES public.vigas(internal_id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_vigas_codigo ON public.vigas USING btree (codigo_viga);
CREATE INDEX IF NOT EXISTS idx_vigas_estado ON public.vigas USING btree (estado);
CREATE INDEX IF NOT EXISTS idx_vigas_proyecto ON public.vigas USING btree (proyecto);
CREATE INDEX IF NOT EXISTS idx_production_log_fecha ON public.production_log USING btree (fecha_operacion);
CREATE INDEX IF NOT EXISTS idx_production_log_viga ON public.production_log USING btree (viga_internal_id);
