import { clienteDeServidor } from "@/lib/supabase/servidor";

export type Aplicacion = {
  clave: string;
  nombre: string;
  descripcion: string;
  icono: string;
  ruta: string;
};

export type QuienEsUsted = {
  id: string;
  nombre: string;
  correo: string;
  esSuperadmin: boolean;
  /** Las áreas a las que esta persona puede entrar. */
  areas: Aplicacion[];
  /** Todas las que existen. Sólo se llena para el superadmin. */
  todasLasAreas: Aplicacion[];
};

/**
 * Quién está mirando y a qué puede entrar.
 *
 * Las membresías no se filtran aquí: las filtra RLS. Esta consulta pide todas
 * y la base devuelve las que corresponden. Es la diferencia entre un permiso
 * que se comprueba una vez y uno que hay que acordarse de comprobar en cada
 * pantalla.
 */
export async function quienEsUsted(): Promise<QuienEsUsted | null> {
  const supabase = await clienteDeServidor();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return null;

  const { data: persona } = await supabase
    .schema("plataforma").from("persona")
    .select("id, nombre, correo, es_superadmin")
    .eq("id", user.id)
    .single();

  const { data: membresias } = await supabase
    .schema("plataforma").from("membresia")
    .select("aplicacion, activa, aplicacion_ref:aplicacion(clave, nombre, descripcion, icono, ruta, activa, orden)")
    .eq("activa", true);

  const areas = (membresias ?? [])
    .map((m) => m.aplicacion_ref as unknown as Aplicacion & { activa: boolean; orden: number })
    .filter((a) => a && a.activa)
    .sort((a, b) => a.orden - b.orden);

  const esSuperadmin = persona?.es_superadmin ?? false;
  let todasLasAreas: Aplicacion[] = [];
  if (esSuperadmin) {
    const { data } = await supabase
      .schema("plataforma").from("aplicacion")
      .select("clave, nombre, descripcion, icono, ruta")
      .eq("activa", true)
      .order("orden");
    todasLasAreas = data ?? [];
  }

  return {
    id: user.id,
    nombre: persona?.nombre ?? user.email ?? "",
    correo: persona?.correo ?? user.email ?? "",
    esSuperadmin,
    areas,
    todasLasAreas,
  };
}
