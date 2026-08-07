import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

/**
 * El cliente de Supabase para lo que corre en el servidor.
 *
 * Usa la clave publicable, no la secreta. Eso es a propósito: quien protege los
 * datos es RLS, no esconder una clave. Con la secreta se saltarían todas las
 * políticas, y entonces cada consulta tendría que acordarse de filtrar por
 * quién pregunta — que es exactamente el descuido que RLS existe para evitar.
 */
export async function clienteDeServidor() {
  const almacen = await cookies();

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return almacen.getAll();
        },
        setAll(nuevas) {
          try {
            nuevas.forEach(({ name, value, options }) =>
              almacen.set(name, value, options),
            );
          } catch {
            // Desde un Server Component no se pueden escribir cookies. No pasa
            // nada: el middleware ya refrescó la sesión antes de llegar aquí.
          }
        },
      },
    },
  );
}
