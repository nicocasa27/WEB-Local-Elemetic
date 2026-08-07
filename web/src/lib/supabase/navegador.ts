import { createBrowserClient } from "@supabase/ssr";

/** El cliente de Supabase para lo que corre en el navegador. */
export function clienteDeNavegador() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
}
