import { NextResponse } from "next/server";
import { clienteDeServidor } from "@/lib/supabase/servidor";

export async function POST(peticion: Request) {
  const supabase = await clienteDeServidor();
  await supabase.auth.signOut();
  return NextResponse.redirect(new URL("/acceso", peticion.url), { status: 303 });
}
