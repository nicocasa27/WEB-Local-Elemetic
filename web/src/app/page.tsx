import Link from "next/link";
import { quienEsUsted } from "@/lib/plataforma";

/**
 * El portal: las áreas a las que esta persona puede entrar.
 *
 * Quien no tiene ninguna no ve un mosaico vacío y una cara de tonto: ve a quién
 * pedirla. Una pantalla en blanco sin explicación es la peor forma de decir
 * «no tienes permiso».
 */
export default async function Portal() {
  const usted = await quienEsUsted();
  if (!usted) return null; // el middleware ya redirigió

  const sinAcceso = usted.areas.length === 0;
  const soloComoSuperadmin = usted.esSuperadmin
    ? usted.todasLasAreas.filter((t) => !usted.areas.some((a) => a.clave === t.clave))
    : [];

  return (
    <main className="mx-auto max-w-4xl px-4 py-10 sm:py-16">
      <header className="mb-10 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.12em] text-indigo-600">
            Elemetic
          </p>
          <h1 className="mt-1 text-3xl font-semibold">Hola, {primerNombre(usted.nombre)}</h1>
          <p className="mt-1 text-zinc-500">
            {sinAcceso ? "Todavía no tienes ningún área asignada." : "¿A dónde vas?"}
          </p>
        </div>
        <form action="/auth/salir" method="post">
          <button className="h-10 rounded-lg border border-zinc-300 bg-white px-4 text-sm font-medium transition hover:bg-zinc-100">
            Salir
          </button>
        </form>
      </header>

      {sinAcceso ? (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6">
          <p className="font-medium text-amber-900">Tu cuenta existe, pero aún no tiene acceso a ningún área.</p>
          <p className="mt-2 text-sm text-amber-800">
            El acceso lo da quien administra cada área, no el portal. Pídeselo a quien
            lleve la que necesites y podrás entrar sin volver a registrarte.
          </p>
        </div>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2">
          {usted.areas.map((area) => (
            <li key={area.clave}>
              <Link
                href={area.ruta}
                className="block h-full rounded-2xl bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 transition hover:shadow-md hover:ring-indigo-500/30"
              >
                <h2 className="text-lg font-semibold">{area.nombre}</h2>
                <p className="mt-1 text-sm text-zinc-500">{area.descripcion}</p>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {soloComoSuperadmin.length > 0 && (
        <section className="mt-10">
          <h2 className="text-sm font-semibold text-zinc-500">Otras áreas que existen</h2>
          <p className="mt-1 text-sm text-zinc-500">
            Las ves porque administras la plataforma. Para entrar necesitas que quien
            lleve el área te dé acceso — ni siquiera un superadmin puede dárselo a sí mismo.
          </p>
          <ul className="mt-3 flex flex-wrap gap-2">
            {soloComoSuperadmin.map((area) => (
              <li
                key={area.clave}
                className="rounded-lg bg-zinc-100 px-3 py-1.5 text-sm text-zinc-600"
              >
                {area.nombre}
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}

function primerNombre(nombre: string) {
  return nombre.trim().split(/\s+/)[0] || nombre;
}
