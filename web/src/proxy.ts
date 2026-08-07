import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

/**
 * Refresca la sesión en cada petición y manda al acceso a quien no la tenga.
 *
 * Va aquí y no en cada página porque una comprobación que hay que acordarse de
 * poner en cuarenta sitios se olvida en el cuarenta y uno, y ese es el que
 * queda abierto.
 *
 * Se llama `proxy` y no `middleware`: en Next 16 el nombre viejo está obsoleto.
 */
export async function proxy(peticion: NextRequest) {
  let respuesta = NextResponse.next({ request: peticion });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return peticion.cookies.getAll();
        },
        setAll(nuevas) {
          nuevas.forEach(({ name, value }) => peticion.cookies.set(name, value));
          respuesta = NextResponse.next({ request: peticion });
          nuevas.forEach(({ name, value, options }) =>
            respuesta.cookies.set(name, value, options),
          );
        },
      },
    },
  );

  // getUser() y no getSession(): getSession lee la cookie sin comprobar la
  // firma, así que se la puede fabricar cualquiera.
  const { data: { user } } = await supabase.auth.getUser();

  const ruta = peticion.nextUrl.pathname;
  const publica = ruta.startsWith("/acceso") || ruta.startsWith("/auth");

  if (!user && !publica) {
    const destino = peticion.nextUrl.clone();
    destino.pathname = "/acceso";
    // A dónde iba, para devolverlo ahí después de entrar.
    destino.searchParams.set("siguiente", ruta);
    return NextResponse.redirect(destino);
  }

  if (user && ruta.startsWith("/acceso")) {
    const destino = peticion.nextUrl.clone();
    destino.pathname = "/";
    destino.search = "";
    return NextResponse.redirect(destino);
  }

  return respuesta;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|webp)$).*)"],
};
